"""대부업체(차주) 마스터 upsert.

식별 우선순위: business_number → company_name. 빈 명칭은 skip.
신규 필드 NULL 입력은 기존 값을 덮어쓰지 않는다 (부분 갱신).
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from models import Lender

logger = logging.getLogger(__name__)


def _norm(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    stripped = s.strip()
    return stripped or None


def upsert(
    db: Session,
    *,
    company_name: Optional[str],
    business_number: Optional[str] = None,
    ceo_name: Optional[str] = None,
    credit_score_nice: Optional[int] = None,
    credit_score_kcb: Optional[int] = None,
) -> Optional[Lender]:
    """입력값으로 대부업체 row 를 upsert. 식별 키가 전혀 없으면 None 반환."""
    company_name = _norm(company_name)
    business_number = _norm(business_number)
    ceo_name = _norm(ceo_name)
    if not company_name and not business_number:
        return None

    row: Optional[Lender] = None
    if business_number:
        row = db.query(Lender).filter(Lender.business_number == business_number).first()
    if row is None and company_name:
        row = (
            db.query(Lender)
            .filter(Lender.company_name == company_name, Lender.business_number.is_(None))
            .first()
        )

    if row is None:
        if not company_name:
            # business_number 만 있고 명칭이 없으면 생성 거부 (명칭이 NOT NULL)
            return None
        row = Lender(
            company_name=company_name,
            business_number=business_number,
            ceo_name=ceo_name,
            credit_score_nice=credit_score_nice,
            credit_score_kcb=credit_score_kcb,
        )
        db.add(row)
    else:
        if company_name:
            row.company_name = company_name
        if business_number and row.business_number != business_number:
            row.business_number = business_number
        if ceo_name:
            row.ceo_name = ceo_name
        if credit_score_nice is not None:
            row.credit_score_nice = credit_score_nice
        if credit_score_kcb is not None:
            row.credit_score_kcb = credit_score_kcb

    db.commit()
    db.refresh(row)
    return row


def upsert_silent(db: Session, **kwargs) -> Optional[Lender]:
    """upsert 의 예외 무시 버전 — 분석/등록 흐름을 막지 않는다."""
    try:
        return upsert(db, **kwargs)
    except Exception as e:
        logger.warning(f"lender upsert 실패 (무시): {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return None
