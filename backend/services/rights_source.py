"""권리분석 데이터 source 디스패처.

`settings.registry_source` 로 DB경로(폐쇄망, 6테이블 결정적 빌드)와 PDF경로(현행
외부 8100→MinerU→LLM)를 선택한다. 출력 dict 계약은 두 경로 동일.
  - "pdf"  : 항상 PDF경로 (현행 — 안전 기본값)
  - "db"   : 항상 DB경로
  - "auto" : rles_unq_no 있으면 DB, 없으면 PDF (전환기)
폐쇄망 컷오버 완료 시 PDF경로 제거 예정 (step5 §1).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from core.config import settings


def get_rights_data(
    db: Session,
    application_id: Optional[str],
    registry_ic_id: Optional[int],
    rles_unq_no: Optional[str],
) -> dict:
    src = settings.registry_source
    use_db = src == "db" or (src == "auto" and bool(rles_unq_no))
    if use_db:
        from services.registry_db_service import build_rights_data
        return build_rights_data(db, application_id, rles_unq_no)
    from services.ai_rights_analysis_service import generate_or_get_cached
    return generate_or_get_cached(db, application_id, registry_ic_id)
