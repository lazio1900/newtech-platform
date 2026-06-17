"""사후 모니터링 라우터: /api/monitoring/* (심사역/관리자만)"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.auth import require_role
from core.database import get_db
from models import User, UserRole
from services import monitoring_service

router = APIRouter()


class MonitoringRegisterRequest(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=200)
    ceo_name: str = Field(..., min_length=1, max_length=80)
    property_address: str = Field(..., min_length=1, max_length=500)
    loan_amount: int = Field(..., gt=0)
    execution_price: int = Field(..., gt=0)
    application_id: str | None = Field(default=None, max_length=36)
    complex_id: int | None = None
    area_id: int | None = None
    prior_claims: int = Field(default=0, ge=0)


@router.get("")
def list_loans(
    user: User = Depends(require_role(UserRole.AUDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    return {
        "loans": monitoring_service.list_loan_dicts(db),
        "summary": monitoring_service.get_summary(db),
    }


@router.get("/{loan_code}")
def get_loan(
    loan_code: str,
    user: User = Depends(require_role(UserRole.AUDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    from core.config import settings as _cfg
    if _cfg.internal_only:
        row = next((r for r in monitoring_service.list_loan_dicts(db) if r["loan_id"] == loan_code), None)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="대출건을 찾을 수 없습니다.")
        return row
    loan = monitoring_service.get_by_loan_code(db, loan_code)
    if not loan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="대출건을 찾을 수 없습니다.")
    return loan.to_dict()


@router.post("")
def register_loan(
    request: MonitoringRegisterRequest,
    auditor: User = Depends(require_role(UserRole.AUDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    loan = monitoring_service.add_loan(
        db,
        auditor=auditor,
        company_name=request.company_name,
        ceo_name=request.ceo_name,
        property_address=request.property_address,
        loan_amount=request.loan_amount,
        execution_price=request.execution_price,
        application_id=request.application_id,
        complex_id=request.complex_id,
        area_id=request.area_id,
        prior_claims=request.prior_claims,
    )
    return {"status": "success", "loan": loan.to_dict()}


@router.post("/reevaluate-all")
def reevaluate_all_loans(
    user: User = Depends(require_role(UserRole.AUDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    result = monitoring_service.reevaluate_all(db)
    return {
        "status": "success",
        **result,
        "loans": monitoring_service.list_loan_dicts(db),
        "summary": monitoring_service.get_summary(db),
    }


@router.post("/{loan_code}/reevaluate")
def reevaluate_loan(
    loan_code: str,
    user: User = Depends(require_role(UserRole.AUDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    loan = monitoring_service.get_by_loan_code(db, loan_code)
    if not loan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="대출건을 찾을 수 없습니다.")
    updated = monitoring_service.reevaluate_loan(db, loan)
    return {"status": "success", "updated": updated, "loan": loan.to_dict()}
