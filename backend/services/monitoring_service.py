"""사후 모니터링 서비스 (DB 기반)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import MonitoringLoan, User


def list_all(db: Session) -> list[MonitoringLoan]:
    return (
        db.query(MonitoringLoan)
        .order_by(MonitoringLoan.execution_date.desc())
        .all()
    )


def list_loan_dicts(db: Session) -> list[dict]:
    """라우터용 행 목록. internal_only 면 정보계 6테이블에서, 아니면 app monitoring_loans."""
    from core.config import settings as _cfg

    if _cfg.internal_only:
        from services.internal_monitoring_service import list_internal_monitoring
        return list_internal_monitoring(db)
    return [l.to_dict() for l in list_all(db)]


def get_by_loan_code(db: Session, loan_code: str) -> Optional[MonitoringLoan]:
    return db.query(MonitoringLoan).filter(MonitoringLoan.loan_code == loan_code).first()


def _next_loan_code(db: Session) -> str:
    """LN-YYYY-NNN 형식. 연도 내 일련번호."""
    year = datetime.utcnow().strftime("%Y")
    prefix = f"LN-{year}-"
    seq = (
        db.query(func.count(MonitoringLoan.id))
        .filter(MonitoringLoan.loan_code.like(f"{prefix}%"))
        .scalar()
    ) or 0
    return f"{prefix}{seq + 1:03d}"


def add_loan(
    db: Session,
    *,
    auditor: User,
    company_name: str,
    ceo_name: str,
    property_address: str,
    loan_amount: int,
    execution_price: int,
    application_id: str | None = None,
    complex_id: int | None = None,
    area_id: int | None = None,
    prior_claims: int = 0,
    execution_date: date | None = None,
) -> MonitoringLoan:
    loan = MonitoringLoan(
        loan_code=_next_loan_code(db),
        application_id=application_id,
        auditor_user_id=auditor.id,
        auditor_name=auditor.ceo_name or auditor.user_id,
        company_name=company_name,
        ceo_name=ceo_name,
        property_address=property_address,
        complex_id=complex_id,
        area_id=area_id,
        loan_amount=loan_amount,
        prior_claims=prior_claims,
        execution_date=execution_date or date.today(),
        execution_price=execution_price,
        current_price=execution_price,  # 초기값 = 집행 시점 시세, 재평가 전까지 동일
    )
    db.add(loan)
    db.commit()
    db.refresh(loan)
    return loan


def reevaluate_loan(db: Session, loan: MonitoringLoan) -> bool:
    """담보 단지의 최신 시세로 current_price 갱신. 단지 식별자(complex_id) 없으면 skip.

    current_price = execution_price 와 동일 정의(KB 추정시세)로 잡아 LTV 변동이
    '같은 자' 위에서 움직이게 한다. 시세 결측이면 명시적 skip(기존값 유지).
    """
    if not loan.complex_id:
        return False
    estimated = _latest_estimated_price(db, loan)
    if not estimated:
        return False
    loan.current_price = estimated
    loan.last_evaluated_at = datetime.utcnow()
    db.commit()
    db.refresh(loan)
    return True


def reevaluate_all(db: Session) -> dict:
    from core.config import settings as _cfg

    if _cfg.internal_only:
        # 정보계는 read-only — current_price 는 조회 시점에 계산되므로 쓰기 재평가 없음
        return {"evaluated": 0, "skipped": 0}
    evaluated = skipped = 0
    for loan in list_all(db):
        if reevaluate_loan(db, loan):
            evaluated += 1
        else:
            skipped += 1
    return {"evaluated": evaluated, "skipped": skipped}


def _latest_estimated_price(db: Session, loan: MonitoringLoan) -> int | None:
    from core.config import settings as _cfg

    if _cfg.internal_only:
        from services.internal_market_service import get_internal_estimated_price
        return get_internal_estimated_price(db, loan.complex_id, loan.area_id)

    from services.real_data_service import get_real_market_data
    md = get_real_market_data(
        db, loan.property_address, complex_id=loan.complex_id, area_id=loan.area_id
    )
    cd = md.get("credit_data")
    if not cd or not cd.kb_price or not cd.kb_price.estimated:
        return None
    return int(cd.kb_price.estimated)


def get_summary(db: Session) -> dict:
    from core.config import settings as _cfg

    if _cfg.internal_only:
        from services.internal_monitoring_service import list_internal_monitoring, summary_from_rows
        return summary_from_rows(list_internal_monitoring(db))
    loans = list_all(db)
    total = len(loans)
    if total == 0:
        return {
            "total_count": 0,
            "green_count": 0,
            "yellow_count": 0,
            "red_count": 0,
            "total_amount": 0,
            "avg_current_ltv": 0.0,
        }
    green = sum(1 for l in loans if l.signal == "green")
    yellow = sum(1 for l in loans if l.signal == "yellow")
    red = sum(1 for l in loans if l.signal == "red")
    return {
        "total_count": total,
        "green_count": green,
        "yellow_count": yellow,
        "red_count": red,
        "total_amount": sum(l.loan_amount for l in loans),
        "avg_current_ltv": round(sum(l.current_ltv for l in loans) / total, 1),
    }
