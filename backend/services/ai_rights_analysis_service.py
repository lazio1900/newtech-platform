"""LLM 기반 등기부등본 권리 분석.

흐름:
  ic_id → 등기부 API 8100 에서 PDF 받기 → pdfplumber 로 텍스트 추출
       → LLM (JSON mode) → {basic, analysis} 반환
       → loan_applications.ai_rights_text 에 캐시
"""
from __future__ import annotations

import io
import json
import logging
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from core.config import settings
from models.loan import LoanApplication

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """당신은 한국 등기부등본 분석 전문가입니다.
주어진 등기부등본 텍스트를 분석해 JSON 으로 반환합니다.

JSON 키:
- "ownership_entries": 갑구 소유지분현황 array. 각 항목은
    {"name": "이OO", "reg_number": "*-*-*", "share": "1/1", "address": "서울특별시...", "rank_number": 1}
- "ownership_other_entries": 갑구 소유권 외 사항 array (가압류/가처분/경매개시 등). 각 항목은
    {"rank_number": 1, "purpose": "가압류", "receipt_info": "2024년...", "details": "..."}
- "mortgage_entries": 을구 (근)저당권/전세권 array. 각 항목은
    {"rank_number": "1-1", "purpose": "근저당권설정", "receipt_info": "2024년...", "main_details": "채권최고액 5억원 / 채무자 이OO / 근저당권자 KB국민은행"}
- "max_bond_amount": 선순위 채권최고액 합계 (원, 정수). 모든 활성 근저당의 채권최고액 합산
- "tenant_deposit": 선순위 임차보증금 (원, 정수). 등기부에 있으면, 없으면 0
- "gap_summary":  갑구 소유권/이전이력 자연어 요약 2~3문장
- "eul_summary":  을구 (근)저당/전세권 자연어 요약 2~3문장
- "seizure_summary": 가압류·가처분·경매 등 권리 침해 자연어 요약 2~3문장 (없으면 "없음" 명시)
- "priority_summary": 선순위/대항력 분석 자연어 2~3문장
- "comprehensive_opinion": 종합 의견 2~3문장 (담보 적격성 관점)

작성 규칙:
- 모든 *_summary 와 comprehensive_opinion 은 한국어 존대형(~합니다) 평문
- 마크다운/번호 금지
- 텍스트에 없는 정보는 추측 금지. 없으면 "기록사항 없음" 또는 빈 array
- 채권최고액·금액은 원 단위 정수 (원문이 "5억" 이면 500000000)
"""


def _fetch_pdf_blob(ic_id: int) -> Optional[bytes]:
    """등기부 API 8100 에서 PDF binary 를 받아온다."""
    if not settings.registry_internal_token:
        logger.warning("REGISTRY_INTERNAL_TOKEN 미설정")
        return None
    try:
        with httpx.Client(timeout=30) as client:
            r = client.get(
                f"{settings.registry_api_url}/v1/registry/{ic_id}/pdf",
                headers={"X-Internal-Token": settings.registry_internal_token},
            )
        if r.status_code != 200:
            logger.warning(f"[ai_rights] PDF fetch {ic_id}: HTTP {r.status_code}")
            return None
        return r.content
    except Exception as e:
        logger.warning(f"[ai_rights] PDF fetch {ic_id} failed: {e}")
        return None


def _extract_text(pdf_bytes: bytes) -> str:
    """PDF 전체 텍스트 추출 (pdfplumber)."""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            return "\n\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception as e:
        logger.warning(f"[ai_rights] text extract failed: {e}")
        return ""


def _flatten(val) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, list):
        return " ".join(_flatten(v) for v in val)
    if isinstance(val, dict):
        return " ".join(f"{k}: {_flatten(v)}" for k, v in val.items())
    return str(val).strip()


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
    }


def generate_or_get_cached(
    db: Session,
    application_id: Optional[str],
    registry_ic_id: Optional[int],
) -> dict:
    """등기부 LLM 분석 결과 dict 반환.

    캐시 우선, 없으면 PDF 추출 + LLM 호출. 실패 시 빈 dict.
    """
    if not registry_ic_id:
        return _empty_result()

    app = None
    if application_id:
        app = db.query(LoanApplication).filter(LoanApplication.id == application_id).first()
        if app and app.ai_rights_text:
            try:
                return json.loads(app.ai_rights_text)
            except json.JSONDecodeError:
                pass  # 캐시 깨짐 → 재생성

    pdf_bytes = _fetch_pdf_blob(registry_ic_id)
    if not pdf_bytes:
        return _empty_result()

    text = _extract_text(pdf_bytes)
    if not text.strip():
        logger.warning(f"[ai_rights] {registry_ic_id}: empty PDF text")
        return _empty_result()

    # PDF 너무 길면 마지막 부분 (요약 페이지) 위주로 자르기 — 일단 전체 사용
    if len(text) > 30000:
        text = text[:30000]

    user_prompt = (
        f"등기부등본 텍스트(ic_id={registry_ic_id}):\n\n{text}\n\n"
        "위 등기부 내용을 시스템 메시지의 JSON 스키마에 맞게 응답하세요."
    )

    try:
        from services.llm_service import LLMClient
        client = LLMClient()
        result = client.complete(user_prompt, system=SYSTEM_PROMPT, json_mode=True)
        raw = (result.get("text") or "").strip()
        if not raw:
            return _empty_result()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"[ai_rights] JSON parse failed: {e}")
            return _empty_result()

        # 응답 정규화 — list 보장, summary 평문화
        out = _empty_result()
        out["ownership_entries"] = parsed.get("ownership_entries") or []
        out["ownership_other_entries"] = parsed.get("ownership_other_entries") or []
        out["mortgage_entries"] = parsed.get("mortgage_entries") or []
        try:
            out["max_bond_amount"] = int(parsed.get("max_bond_amount") or 0)
        except (ValueError, TypeError):
            out["max_bond_amount"] = 0
        try:
            out["tenant_deposit"] = int(parsed.get("tenant_deposit") or 0)
        except (ValueError, TypeError):
            out["tenant_deposit"] = 0
        out["gap_summary"] = _flatten(parsed.get("gap_summary"))
        out["eul_summary"] = _flatten(parsed.get("eul_summary"))
        out["seizure_summary"] = _flatten(parsed.get("seizure_summary"))
        out["priority_summary"] = _flatten(parsed.get("priority_summary"))
        out["comprehensive_opinion"] = _flatten(parsed.get("comprehensive_opinion"))

        if app:
            app.ai_rights_text = json.dumps(out, ensure_ascii=False)
            app.ai_rights_generated_at = datetime.utcnow()
            db.commit()
            logger.info(
                f"[ai_rights] cached for application {application_id} "
                f"(in={result.get('prompt_tokens')}, out={result.get('completion_tokens')})"
            )
        return out
    except Exception as e:
        logger.warning(f"[ai_rights] LLM call failed: {e}")
        return _empty_result()
