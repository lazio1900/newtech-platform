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
    execution_date: date | None = None,
) -> MonitoringLoan:
    loan = MonitoringLoan(
        loan_code=_next_loan_code(db),
        auditor_user_id=auditor.id,
        auditor_name=auditor.ceo_name or auditor.user_id,
        company_name=company_name,
        ceo_name=ceo_name,
        property_address=property_address,
        loan_amount=loan_amount,
        execution_date=execution_date or date.today(),
        execution_price=execution_price,
        current_price=execution_price,  # 초기값 = 집행 시점 시세
    )
    db.add(loan)
    db.commit()
    db.refresh(loan)
    return loan


def get_summary(db: Session) -> dict:
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
