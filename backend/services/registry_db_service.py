"""NICE 등기부 6테이블 → PropertyRightsData 결정적 빌드 (폐쇄망 권리분석).

step5 설계(internal-migration-registry-db-service-design.md). 2층 구조:
  - 결정적층(LLM 무관, 항상 채움): 엔트리 3종 + max_bond_amount(SUM 근저당) +
    tenant_deposit + 신선도(inquiry_date)/카운트.
  - 요약층(사내 LLM, LLMClient/ADR-008): *_summary 4종 + comprehensive_opinion.
    입력은 결정적층 JSON(OCR markdown 아님) → MinerU·critique 루프 불필요.

출력 dict 계약은 ai_rights_analysis_service._empty_result 와 동일(+ inquiry_date/카운트 additive).
소비부(analysis_service)는 .get() 으로 읽으므로 추가 키는 무해.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import nullslast
from sqlalchemy.orm import Session

from models.loan import LoanApplication
from models.registry_nice import (
    NiceRlesBasic,
    NiceRlesBrief,
    NiceRlesCollateral,
    NiceRlesDetail,
    NiceRlesHeader,
)

logger = logging.getLogger(__name__)

# 등기목적 분류 — 텍스트(rgty_prps_ctnt) 기반. 코드 master 확정 전까지 robust (step4 §3 규칙).
_GEUNJEODANG_SETTING = "근저당권설정"  # max_bond 합산 대상(정확 일치 — 변경/이전/질권 제외)
_JEONSE_SETTING = "전세권설정"  # tenant_deposit 합산 대상(정확 일치 — 변경/이전 제외, max_bond 와 대칭)
# 갑구 소유권 외(권리침해) 목적 키워드
_GAP_OTHER_KEYWORDS = ("압류", "가압류", "가처분", "경매")
# 표제부 코드
_HDR_JIBEON = "C11"
_HDR_ROAD = "C12"
_HDR_HO = "E43"

_SUMMARY_SYSTEM = """당신은 한국 등기부등본 분석 전문가입니다.
주어진 '구조화된 권리 데이터(JSON)'만을 근거로 각 항목 요약을 작성합니다.
- 한국어 존대형(~합니다) 평문. 마크다운/번호/이모지 금지.
- 데이터에 없는 내용은 추측하지 마세요. 해당 사항이 없으면 "없음" 으로 명시.
반드시 아래 키를 가진 JSON 으로만 응답하세요:
{"gap_summary","eul_summary","seizure_summary","priority_summary","comprehensive_opinion"}
- gap_summary: 갑구 소유권 현황 요약
- eul_summary: 을구 (근)저당/전세권 요약 (채권최고액 합계 포함)
- seizure_summary: 압류·가압류·가처분·경매 등 권리침해 요약
- priority_summary: 선순위/대항력 관점 요약
- comprehensive_opinion: 담보 적격성 관점 종합 의견"""


def _empty_result() -> dict:
    return {
        "ownership_entries": [],
        "ownership_other_entries": [],
        "mortgage_entries": [],
        "max_bond_amount": 0,
        "tenant_deposit": 0,
        "gap_summary": "",
        "eul_summary": "",
        "seizure_summary": "",
        "priority_summary": "",
        "comprehensive_opinion": "",
        "property_address": "",
        "inquiry_date": "",
        "seizure_count": 0,
        "prov_seizure_count": 0,
        "provisional_disp_count": 0,
        "auction_count": 0,
        "mortgage_count": 0,
    }


def _mask_rnno(_raw: Optional[str]) -> str:
    """실명번호 마스킹(ADR-010). 복호 모듈 없이도 노출은 마스킹 형태로 고정."""
    if not _raw:
        return ""
    return "******-*******"


def _to_int(v) -> int:
    try:
        return int(str(v).strip())
    except (ValueError, TypeError, AttributeError):
        return 0


def _digits(v: Optional[str]) -> str:
    """부동산고유번호 정규화 — 하이픈/공백 제거. 두 입력경로(신청 create / 직접 analyze) 통일."""
    return "".join(ch for ch in (v or "") if ch.isdigit())


def _fmt_receipt(dt: Optional[str], no: Optional[str]) -> str:
    parts = [p for p in (dt, no) if p]
    return "\n".join(parts)


def _fmt_mortgage_details(c: NiceRlesCollateral) -> str:
    lines = []
    if c.pdl_amt_ctnt:
        lines.append(f"채권최고액 {c.pdl_amt_ctnt}")
    elif c.pdl_amt:
        lines.append(f"채권최고액 금{int(c.pdl_amt):,}원")
    if c.rtp_nm:
        lines.append(f"권리자 {c.rtp_nm}")
    return "\n".join(lines)


def registry_exists(db: Session, rles_unq_no: str) -> bool:
    """기본행 존재 여부(행 존재만 확인 — 복호화 불필요). 신청 폼 입력 가드용."""
    rles_unq_no = _digits(rles_unq_no)
    if len(rles_unq_no) != 14:
        return False
    return (
        db.query(NiceRlesBasic.id)
        .filter(NiceRlesBasic.rles_unq_no == rles_unq_no)
        .first()
        is not None
    )


def _latest_basics(db: Session) -> dict:
    """rles_unq_no → 최신 스냅샷(IQRY_DT 최대) 기본행."""
    latest: dict = {}
    for b in (
        db.query(NiceRlesBasic)
        .order_by(NiceRlesBasic.rles_unq_no, nullslast(NiceRlesBasic.iqry_dt.desc()))
        .all()
    ):
        latest.setdefault(b.rles_unq_no, b)
    return latest


def search_registries(
    db: Session,
    *,
    sido: Optional[str] = None,
    sigungu: Optional[str] = None,
    dong: Optional[str] = None,
    complex_name: Optional[str] = None,
    building: Optional[str] = None,
    unit: Optional[str] = None,
    limit: int = 20,
) -> list:
    """적재된 등기부(nice_rles_*) 중 주소 토큰으로 부동산고유번호 후보 검색.

    사내 심사시스템의 고유번호 검색은 앱에서 호출 불가 → 앱이 미러한 등기부 한정
    (dev=샘플, prod=수집기가 미러한 물건). 향후 사내 디렉토리가 열리면 이 함수만 교체.

    gate=시군구(필수 좁힘), boost=시도·읍면동·단지명·동·호(랭킹). 읍면동은 법정동/행정동
    표기차로 gate 에 두면 오탈락하므로 boost 로 둔다. 표제부 평문 전부를 blob 으로
    파이썬 substring(in) 매칭(C11 지번에 단지·동, E43 에 호가 들어있음, 대소문자 구분).
    """
    latest = _latest_basics(db)
    if not latest:
        return []

    msgms = {b.nice_msgm_no for b in latest.values()}
    blobs: dict = {}
    for h in (
        db.query(NiceRlesHeader)
        .filter(NiceRlesHeader.nice_msgm_no.in_(msgms))
        .all()
    ):
        if h.hdr_ctnt:
            blobs.setdefault(h.rles_unq_no, {}).setdefault(h.hdr_dtl_cd, h.hdr_ctnt)

    gate = [t.strip() for t in (sigungu,) if t and t.strip()]
    boost = [t.strip() for t in (sido, dong, complex_name) if t and t.strip()]
    # 동/호는 접미사 포함('제105동'/'제302호')으로 매칭해 단일 숫자 오탐을 줄임
    if building and building.strip():
        boost.append(f"{building.strip()}동")
    if unit and unit.strip():
        boost.append(f"{unit.strip()}호")
    if not gate and not boost:
        return []

    out = []
    for unq, b in latest.items():
        hdr = blobs.get(unq, {})
        blob = " ".join(hdr.values())
        if gate and not all(g in blob for g in gate):
            continue
        score = sum(1 for t in gate + boost if t in blob)
        out.append({
            "rles_unq_no": unq,
            "road_address": hdr.get(_HDR_ROAD, ""),
            "jibun_address": hdr.get(_HDR_JIBEON, ""),
            "unit": hdr.get(_HDR_HO, ""),
            "mortgage_count": b.fxcl_ccnt or 0,
            "seizure_count": b.seiz_ccnt or 0,
            "inquiry_date": b.iqry_dt or "",
            "_score": score,
        })

    out.sort(key=lambda r: (r["_score"], r["inquiry_date"]), reverse=True)
    for r in out:
        del r["_score"]
    return out[:limit]


def build_preview(db: Session, rles_unq_no: str) -> dict:
    """선택/입력한 부동산고유번호의 등기부 결정적 요약(LLM 없음, 폼 조회용)."""
    rles_unq_no = _digits(rles_unq_no)
    det = _build_deterministic(db, rles_unq_no) if len(rles_unq_no) == 14 else None
    if det is None:
        return {"rles_unq_no": rles_unq_no, "exists": False}
    return {
        "rles_unq_no": rles_unq_no,
        "exists": True,
        "property_address": det.get("property_address", ""),
        "inquiry_date": det["inquiry_date"],
        "mortgage_count": det["mortgage_count"],
        "seizure_count": det["seizure_count"],
        "max_bond_amount": det["max_bond_amount"],
        "owners": [e["name"] for e in det["ownership_entries"] if e.get("name")],
    }


def _current_inquiry_date(db: Session, rles_unq_no: str) -> Optional[str]:
    row = (
        db.query(NiceRlesBasic.iqry_dt)
        .filter(NiceRlesBasic.rles_unq_no == rles_unq_no)
        .order_by(nullslast(NiceRlesBasic.iqry_dt.desc()))
        .first()
    )
    return row[0] if row else None


def _build_deterministic(db: Session, rles_unq_no: str) -> Optional[dict]:
    """6테이블 SELECT 만으로 채우는 결정적층. 기본행 없으면 None."""
    # 최신 스냅샷 = IQRY_DT 최대인 기본행. 그 NICE_MSGM_NO 로 자식 테이블을 조인(다중 조회 격리).
    basic = (
        db.query(NiceRlesBasic)
        .filter(NiceRlesBasic.rles_unq_no == rles_unq_no)
        .order_by(nullslast(NiceRlesBasic.iqry_dt.desc()))
        .first()
    )
    if not basic:
        return None
    msgm = basic.nice_msgm_no

    out = _empty_result()
    out["inquiry_date"] = basic.iqry_dt or ""
    out["seizure_count"] = basic.seiz_ccnt or 0
    out["prov_seizure_count"] = basic.prsz_ccnt or 0
    out["provisional_disp_count"] = basic.pvsl_ccnt or 0
    out["auction_count"] = basic.auct_opng_ccnt or 0
    out["mortgage_count"] = basic.fxcl_ccnt or 0

    # 표제부 평문 주소(C12 도로명 우선, 없으면 C11 지번) — 암호화된 소재/거주지 회피
    headers = (
        db.query(NiceRlesHeader)
        .filter(
            NiceRlesHeader.rles_unq_no == rles_unq_no,
            NiceRlesHeader.nice_msgm_no == msgm,
        )
        .all()
    )
    hdr = {h.hdr_dtl_cd: (h.hdr_ctnt or "") for h in headers if h.hdr_ctnt}
    property_addr = hdr.get(_HDR_ROAD) or hdr.get(_HDR_JIBEON) or ""
    out["property_address"] = property_addr

    # 소유자 (요약명세 BRF_I)
    for b in (
        db.query(NiceRlesBrief)
        .filter(
            NiceRlesBrief.rles_unq_no == rles_unq_no,
            NiceRlesBrief.nice_msgm_no == msgm,
        )
        .all()
    ):
        out["ownership_entries"].append({
            "name": b.rgty_nmnr_nm or "",
            "reg_number": _mask_rnno(b.rnno),
            "share": b.own_last_shrs_ctnt or "",
            "address": property_addr,
            "rank_number": _to_int(b.rgty_rank_no),
        })

    # 저당명세 (COLL_I) — 현재 유효분. purpose(텍스트)로 합산 분기.
    max_bond = 0
    tenant = 0
    for c in (
        db.query(NiceRlesCollateral)
        .filter(
            NiceRlesCollateral.rles_unq_no == rles_unq_no,
            NiceRlesCollateral.nice_msgm_no == msgm,
        )
        .all()
    ):
        purpose = (c.rgty_prps_ctnt or "").strip()
        out["mortgage_entries"].append({
            "rank_number": str(c.rgty_rank_no or ""),
            "purpose": purpose,
            "receipt_info": _fmt_receipt(c.rgty_actc_dt, c.rgty_actc_no),
            "main_details": _fmt_mortgage_details(c),
            "target_owner": c.trgt_ownr_nm or "",
        })
        amt = int(c.pdl_amt or 0)
        if purpose == _GEUNJEODANG_SETTING:
            max_bond += amt
        elif purpose == _JEONSE_SETTING:
            tenant += amt
    out["max_bond_amount"] = max_bond
    out["tenant_deposit"] = tenant

    # 갑구 소유권 외 (상세 CCRG_D, ccrg_dvcd=1, 압류류)
    for d in (
        db.query(NiceRlesDetail)
        .filter(
            NiceRlesDetail.rles_unq_no == rles_unq_no,
            NiceRlesDetail.nice_msgm_no == msgm,
            NiceRlesDetail.ccrg_dvcd == "1",
        )
        .all()
    ):
        purpose = (d.rgty_prps_ctnt or "").strip()
        if any(k in purpose for k in _GAP_OTHER_KEYWORDS):
            out["ownership_other_entries"].append({
                "rank_number": _to_int(d.ccrg_rank_no),
                "purpose": purpose,
                "receipt_info": _fmt_receipt(d.rgty_actc_dt, d.rgty_actc_no),
                "details": "",
            })

    return out


def _fill_summaries(out: dict) -> None:
    """요약층 — 사내 LLM(LLMClient)에 결정적층 JSON 을 넘겨 서술 요약 생성.

    실패(연결 미설정·호출 오류) 시 호출자가 잡고 요약은 빈 값 유지(silent fake 금지).
    """
    from services.llm_service import LLMClient

    payload = {
        k: out[k]
        for k in (
            "ownership_entries",
            "ownership_other_entries",
            "mortgage_entries",
            "max_bond_amount",
            "tenant_deposit",
            "seizure_count",
            "prov_seizure_count",
            "provisional_disp_count",
            "auction_count",
        )
    }
    prompt = (
        "다음은 등기부등본 6테이블에서 결정적으로 추출한 권리 데이터(JSON)입니다.\n"
        "이 데이터만 근거로 시스템 메시지의 JSON 스키마에 맞게 요약을 작성하세요.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    client = LLMClient()
    res = client.complete(prompt, system=_SUMMARY_SYSTEM, json_mode=True)
    raw = (res.get("text") or "").strip()
    if not raw:
        return
    parsed = json.loads(raw)
    for k in (
        "gap_summary",
        "eul_summary",
        "seizure_summary",
        "priority_summary",
        "comprehensive_opinion",
    ):
        v = parsed.get(k)
        if isinstance(v, str):
            out[k] = v


def build_rights_data(
    db: Session,
    application_id: Optional[str],
    rles_unq_no: Optional[str],
) -> dict:
    """부동산고유번호로 6테이블 조회 → PropertyRightsData dict(결정적 빌드 + 사내 LLM 요약).

    캐시 우선(스냅샷 inquiry_date 일치 시). 6테이블에 행 없으면 빈 결과(더미 폴백 안 함).
    """
    rles_unq_no = _digits(rles_unq_no)
    if len(rles_unq_no) != 14:
        return _empty_result()

    app = None
    if application_id:
        app = (
            db.query(LoanApplication)
            .filter(LoanApplication.id == application_id)
            .first()
        )
        if app and app.ai_rights_text:
            try:
                cached = json.loads(app.ai_rights_text)
            except json.JSONDecodeError:
                cached = None
            if cached and cached.get("inquiry_date"):
                # 스냅샷 갱신 감지 — 캐시 inquiry_date == 현재 DB inquiry_date 일 때만 재사용
                if cached["inquiry_date"] == (_current_inquiry_date(db, rles_unq_no) or ""):
                    return cached

    deterministic = _build_deterministic(db, rles_unq_no)
    if deterministic is None:
        logger.warning(f"[registry_db] {rles_unq_no}: 6테이블에 행 없음 (등기 조회 선행 필요)")
        return _empty_result()

    out = deterministic
    try:
        _fill_summaries(out)
    except Exception as e:
        # 결정적층(엔트리·금액·LTV)은 유지, 요약만 빈 값. 가짜 요약 생성 금지.
        logger.warning(f"[registry_db] 요약 LLM 실패(결정적층 유지): {e}")

    if app:
        app.ai_rights_text = json.dumps(out, ensure_ascii=False)
        app.ai_rights_generated_at = datetime.utcnow()
        db.commit()

    return out
