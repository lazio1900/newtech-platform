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


@router.get("")
def list_loans(
    user: User = Depends(require_role(UserRole.AUDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    return {
        "loans": [l.to_dict() for l in monitoring_service.list_all(db)],
        "summary": monitoring_service.get_summary(db),
    }


@router.get("/{loan_code}")
def get_loan(
    loan_code: str,
    user: User = Depends(require_role(UserRole.AUDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
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
    )
    return {"status": "success", "loan": loan.to_dict()}
