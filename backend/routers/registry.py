"""등기부등본 발급 라우터 (등기부등본api 8100 으로 proxy).

흐름:
  POST /api/registry/request  → 등기부 8100 /v1/registry/request 로 forward
  GET  /api/registry/{ic_id}  → 상태 조회
  GET  /api/registry/{ic_id}/pdf → PDF 스트림

등기부 API 가 X-Internal-Token 인증을 요구하므로 backend 가 토큰을 추가해 forward.
"""
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.auth import get_current_user
from core.config import settings
from models import User

router = APIRouter()


class RegistryRequestPayload(BaseModel):
    address: str
    dong: Optional[str] = None
    ho: Optional[str] = None
    type: Optional[str] = "집합건물"
    listing_id: Optional[int] = None
    force_refresh: bool = False


def _registry_headers() -> dict:
    if not settings.registry_internal_token:
        raise HTTPException(
            status_code=503,
            detail="등기부등본 API 가 설정되지 않았습니다 (REGISTRY_INTERNAL_TOKEN 미지정)",
        )
    return {"X-Internal-Token": settings.registry_internal_token}


@router.post("/request")
def request_registry(
    payload: RegistryRequestPayload,
    user: User = Depends(get_current_user),
):
    """등기부 발급 요청. 사용자 ID 를 requester_id 로 첨부해 forward."""
    body = payload.model_dump()
    body["requester_id"] = str(user.id)
    if body.get("listing_id") is not None:
        body["listing_id"] = str(body["listing_id"])

    try:
        with httpx.Client(timeout=settings.registry_request_timeout) as client:
            r = client.post(
                f"{settings.registry_api_url}/v1/registry/request",
                json=body,
                headers=_registry_headers(),
            )
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"등기부 API 통신 실패: {e}",
        )

    if r.status_code >= 400:
        # 등기부 API 의 detail 그대로 전달 (사용자에게 매칭실패/한도/킬스위치 메시지 노출)
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        raise HTTPException(status_code=r.status_code, detail=detail)
    return r.json()


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
