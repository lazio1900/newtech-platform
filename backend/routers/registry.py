"""등기부등본 발급 라우터 (등기부등본api 8100 으로 proxy).

흐름:
  POST /api/registry/request  → 등기부 8100 /v1/registry/request 로 forward
  GET  /api/registry/{ic_id}  → 상태 조회
  GET  /api/registry/{ic_id}/pdf → PDF 스트림

등기부 API 가 X-Internal-Token 인증을 요구하므로 backend 가 토큰을 추가해 forward.
"""
import logging
import re
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.config import settings
from core.database import get_db
from models import User

logger = logging.getLogger(__name__)

router = APIRouter()


class RegistryRequestPayload(BaseModel):
    address: str
    dong: Optional[str] = None
    ho: Optional[str] = None
    type: Optional[str] = "집합건물"
    listing_id: Optional[int] = None
    complex_id: Optional[int] = None  # backend 가 지번/도로명 후보 chain 구성용
    building_name: Optional[str] = None  # Daum 우편번호 popup 결과 (선택)
    force_refresh: bool = False


def _registry_headers() -> dict:
    if not settings.registry_internal_token:
        raise HTTPException(
            status_code=503,
            detail="등기부등본 API 가 설정되지 않았습니다 (REGISTRY_INTERNAL_TOKEN 미지정)",
        )
    return {"X-Internal-Token": settings.registry_internal_token}


def _call_upstream_registry(body: dict) -> "httpx.Response":
    """등기부 API 호출. httpx.Response 반환 (caller 가 status/json 처리)."""
    with httpx.Client(timeout=settings.registry_request_timeout) as client:
        return client.post(
            f"{settings.registry_api_url}/v1/registry/request",
            json=body,
            headers=_registry_headers(),
        )


def _is_no_match_failure(resp_json: dict) -> bool:
    """upstream 응답이 IROS '검색 결과 없음' 인지."""
    status = (resp_json.get("status") or "").lower()
    err = str(resp_json.get("error_message") or "")
    return status == "failed" and "검색 결과" in err


_PAREN_RE = re.compile(r"\(([^()]+)\)")


def _name_variants(name: str) -> list[str]:
    """KB 단지명 → IROS 매칭용 표기 변형.

    KB 는 시공사를 괄호로 표기 ("아름마을(효성)") 하지만 IROS 등기부에는
    괄호가 없거나 공백으로 분리된 경우가 많다. 원본 표기 우선, 변형은 보조.
    """
    out: list[str] = [name]
    if _PAREN_RE.search(name):
        spaced = _PAREN_RE.sub(lambda m: f" {m.group(1)}", name)
        out.append(" ".join(spaced.split()))  # 다중 공백 정규화
        out.append(_PAREN_RE.sub(lambda m: m.group(1), name))  # 괄호 제거(공백 없음)
    # 중복 제거 (순서 보존)
    seen: set[str] = set()
    uniq: list[str] = []
    for v in out:
        v = v.strip()
        if v and v not in seen:
            uniq.append(v)
            seen.add(v)
    return uniq


def _build_address_candidates(complex_obj, building_name: Optional[str]) -> list[str]:
    """IROS 매칭률 ↑ 를 위한 후보 주소.

    순서 (코드상 단지명을 도로검색기 단지명보다 먼저, 동·호는 service 에서 append):
      1. 지번 + 코드 단지명 (complex.name)
      2. 도로명 + 코드 단지명
      3. 지번 + Daum 단지명 (building_name)
      4. 도로명 + Daum 단지명
    코드 단지명에 괄호가 있으면 "괄호→공백" / "괄호 제거" 변형을 같은 단계의
    보조 후보로 끼워 넣는다 (예: "아름마을(효성)" → "아름마을 효성" / "아름마을효성").
    """
    candidates: list[str] = []
    seen: set[str] = set()

    def add(addr: str) -> None:
        v = addr.strip()
        if v and v not in seen:
            candidates.append(v)
            seen.add(v)

    jibun = (complex_obj.address or "").strip()
    road = (complex_obj.road_address or "").strip()
    code_name = (complex_obj.name or "").strip()
    daum_name = (building_name or "").strip()

    if code_name:
        for variant in _name_variants(code_name):
            if jibun:
                add(f"{jibun} {variant}")
            if road:
                add(f"{road} {variant}")
    if daum_name:
        for variant in _name_variants(daum_name):
            if jibun:
                add(f"{jibun} {variant}")
            if road:
                add(f"{road} {variant}")
    return candidates


@router.post("/request")
def request_registry(
    payload: RegistryRequestPayload,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """등기부 발급 요청. complex_id 가 있으면 4단계 후보 chain 으로 매칭률 ↑.

    후보 순서 (complex_id 있을 때):
      1) 지번 (단지명 없이)
      2) 도로명 (단지명 없이)
      3) 지번 + Daum 단지명 (popup 사용 시)
      4) 도로명 + Daum 단지명 (popup 사용 시)

    complex_id 없으면 payload.address 그대로 1회만 시도.
    각 후보를 순차 호출, "검색 결과 없음" 이면 다음 후보로. 첫 성공 시 즉시 반환.
    """
    body = payload.model_dump()
    # backend 내부 보강용 필드 제거 — upstream 등기부 API 가 모르는 키
    body.pop("complex_id", None)
    body.pop("building_name", None)
    body["requester_id"] = str(user.id)
    if body.get("listing_id") is not None:
        body["listing_id"] = str(body["listing_id"])

    candidates: list[str] = []
    if payload.complex_id:
        from models.complex import Complex
        co = db.query(Complex).filter(Complex.id == payload.complex_id).first()
        if co:
            candidates = _build_address_candidates(co, payload.building_name)
    if not candidates:
        candidates = [payload.address]

    logger.info(f"[registry] {len(candidates)}개 후보 chain: {candidates}")

    last_resp_json: Optional[dict] = None
    last_http_error: Optional[tuple[int, str]] = None
    for idx, cand in enumerate(candidates, 1):
        cand_body = dict(body, address=cand)
        try:
            r = _call_upstream_registry(cand_body)
        except httpx.HTTPError as e:
            logger.warning(f"[registry] 후보#{idx} httpx error ({cand}): {e}")
            continue

        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except Exception:
                detail = r.text
            logger.warning(f"[registry] 후보#{idx} upstream {r.status_code}: {detail[:200] if isinstance(detail, str) else detail}")
            last_http_error = (r.status_code, detail if isinstance(detail, str) else str(detail))
            continue

        resp_json = r.json()
        if _is_no_match_failure(resp_json):
            logger.info(f"[registry] 후보#{idx} 매칭 실패: {cand}")
            last_resp_json = resp_json
            continue

        logger.info(f"[registry] 후보#{idx} 매칭 성공: {cand} → ic_id={resp_json.get('ic_id')}")
        return resp_json

    # 모든 후보 실패
    if last_resp_json is not None:
        return last_resp_json  # status='failed', error_message='검색 결과가 없습니다.' 그대로
    if last_http_error is not None:
        raise HTTPException(status_code=last_http_error[0], detail=last_http_error[1])
    raise HTTPException(status_code=502, detail="등기부 API 통신 실패")


@router.get("/{ic_id}")
def get_registry(
    ic_id: int,
    user: User = Depends(get_current_user),
):
    """발급 상태 조회 (frontend 폴링용)."""
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(
                f"{settings.registry_api_url}/v1/registry/{ic_id}",
                headers=_registry_headers(),
            )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"등기부 API 통신 실패: {e}")

    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        raise HTTPException(status_code=r.status_code, detail=detail)
    return r.json()


@router.get("/{ic_id}/area")
def get_registry_area(
    ic_id: int,
    complex_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """등기부 markdown 의 표제부에서 전용면적 추출 + 단지 area 중 가장 가까운 평형 추천.

    응답:
      {
        "exclusive_m2": 49.77,             # 등기부에서 추출 (null 가능)
        "suggested_area_id": 12,           # 가장 가까운 KB area (null 가능)
        "areas": [{id, exclusive_m2, pyeong}...]  # 수정용 후보 목록
      }
    """
    from models.complex import Area
    from services.registry_area_extractor import extract_exclusive_m2

    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(
                f"{settings.registry_api_url}/v1/registry/{ic_id}/markdown",
                headers=_registry_headers(),
            )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"등기부 API 통신 실패: {e}")

    exclusive_m2: Optional[float] = None
    if r.status_code == 200:
        md = (r.json() or {}).get("markdown") or ""
        exclusive_m2 = extract_exclusive_m2(md)
    elif r.status_code != 404:
        # 202(처리중) 등은 추출 실패로만 처리 — UI 는 수동 선택 fallback
        logger.info(f"[registry_area] ic_id={ic_id} markdown unavailable: HTTP {r.status_code}")

    areas = (
        db.query(Area)
        .filter(Area.complex_id == complex_id)
        .order_by(Area.exclusive_m2.asc())
        .all()
    )
    suggested_area_id: Optional[int] = None
    if exclusive_m2 is not None and areas:
        suggested = min(areas, key=lambda a: abs((a.exclusive_m2 or 0) - exclusive_m2))
        suggested_area_id = suggested.id

    return {
        "exclusive_m2": exclusive_m2,
        "suggested_area_id": suggested_area_id,
        "areas": [
            {"id": a.id, "exclusive_m2": a.exclusive_m2, "pyeong": a.pyeong}
            for a in areas
        ],
    }


@router.get("/{ic_id}/pdf")
def get_registry_pdf(
    ic_id: int,
    user: User = Depends(get_current_user),
):
    """PDF 바이너리 stream (등기부 API 의 FileResponse 를 그대로 전달)."""
    try:
        client = httpx.Client(timeout=30)
        r = client.get(
            f"{settings.registry_api_url}/v1/registry/{ic_id}/pdf",
            headers=_registry_headers(),
        )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"등기부 API 통신 실패: {e}")

    if r.status_code == 202:
        # 처리중
        try:
            client.close()
        except Exception:
            pass
        raise HTTPException(status_code=202, detail=r.json().get("detail"))
    if r.status_code >= 400:
        try:
            client.close()
        except Exception:
            pass
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return StreamingResponse(
        iter([r.content]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="registry_{ic_id}.pdf"'},
    )
