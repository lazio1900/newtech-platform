"""대출 신청 서비스 (DB 기반)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from models import ALLOWED_TRANSITIONS, ApplicationStatus, LoanApplication, User


def submit(
    db: Session,
    *,
    applicant: User,
    company_name: str,
    ceo_name: str,
    property_address: str,
    loan_amount: int,
    loan_duration: int = 12,
    complex_id: Optional[int] = None,
    complex_name: Optional[str] = None,
    area_id: Optional[int] = None,
    exclusive_m2: Optional[float] = None,
    pyeong: Optional[int] = None,
    dong: Optional[str] = None,
    ho: Optional[str] = None,
    registry_ic_id: Optional[int] = None,
) -> LoanApplication:
    app = LoanApplication(
        id=str(uuid.uuid4())[:8],
        applicant_user_id=applicant.id,
        company_name=company_name,
        ceo_name=ceo_name,
        property_address=property_address,
        loan_amount=loan_amount,
        loan_duration=loan_duration,
        status=ApplicationStatus.RECEIVED,
        complex_id=complex_id,
        complex_name=complex_name,
        area_id=area_id,
        exclusive_m2=exclusive_m2,
        pyeong=pyeong,
        dong=dong,
        ho=ho,
        registry_ic_id=registry_ic_id,
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


def get_by_id(db: Session, app_id: str) -> Optional[LoanApplication]:
    return db.query(LoanApplication).filter(LoanApplication.id == app_id).first()


def list_for_applicant(db: Session, applicant_user_id: int) -> list[LoanApplication]:
    return (
        db.query(LoanApplication)
        .filter(LoanApplication.applicant_user_id == applicant_user_id)
        .order_by(LoanApplication.created_at.desc())
        .all()
    )


def list_all(db: Session) -> list[LoanApplication]:
    return (
        db.query(LoanApplication)
        .order_by(LoanApplication.created_at.desc())
        .all()
    )


def update_status(
    db: Session,
    *,
    app_id: str,
    new_status: ApplicationStatus,
    auditor: User,
    memo: str | None = None,
) -> Optional[LoanApplication]:
    """상태 전이 검증 후 업데이트. 허용되지 않은 전이는 ValueError."""
    app = get_by_id(db, app_id)
    if not app:
        return None

    current = app.status if isinstance(app.status, ApplicationStatus) else ApplicationStatus(app.status)
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if new_status not in allowed and new_status != current:
        raise ValueError(f"invalid status transition: {current.value} → {new_status.value}")

    app.status = new_status
    if memo is not None:
        app.memo = memo
    if app.auditor_user_id is None:
        app.auditor_user_id = auditor.id
    if new_status in (ApplicationStatus.APPROVED, ApplicationStatus.REJECTED):
        app.decided_at = datetime.utcnow()

    db.commit()
    db.refresh(app)
    return app
