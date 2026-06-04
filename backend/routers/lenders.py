"""대부업체(차주) 마스터 CRUD: /api/lenders

권한: AUDITOR/ADMIN. 직접조회에서 select 할 후보를 명시적으로 관리한다.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.auth import require_role
from core.database import get_db
from models import Lender, User, UserRole


router = APIRouter()


class YearlyFinancialIn(BaseModel):
    year: int = Field(..., ge=1900, le=2200)
    assets: Optional[int] = None
    liabilities: Optional[int] = None
    equity: Optional[int] = None
    revenue: Optional[int] = None
    operating_profit: Optional[int] = None
    net_income: Optional[int] = None


class LenderCreateRequest(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=200)
    business_number: Optional[str] = Field(None, max_length=20)
    ceo_name: Optional[str] = Field(None, max_length=80)
    credit_score_nice: Optional[int] = Field(None, ge=0, le=1000)
    credit_score_kcb: Optional[int] = Field(None, ge=0, le=1000)
    direct_debt: Optional[int] = Field(None, ge=0, description="직접채무(원)")
    guarantee_debt: Optional[int] = Field(None, ge=0, description="보증채무(원)")
    financial_data: Optional[List[YearlyFinancialIn]] = Field(None, description="최근 3개년 재무")


class LenderUpdateRequest(BaseModel):
    company_name: Optional[str] = Field(None, min_length=1, max_length=200)
    business_number: Optional[str] = Field(None, max_length=20)
    ceo_name: Optional[str] = Field(None, max_length=80)
    credit_score_nice: Optional[int] = Field(None, ge=0, le=1000)
    credit_score_kcb: Optional[int] = Field(None, ge=0, le=1000)
    direct_debt: Optional[int] = Field(None, ge=0)
    guarantee_debt: Optional[int] = Field(None, ge=0)
    financial_data: Optional[List[YearlyFinancialIn]] = None


def _norm(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    stripped = s.strip()
    return stripped or None


@router.get("")
def list_lenders(
    q: Optional[str] = Query(None, description="명칭/사업자번호 부분일치"),
    _: User = Depends(require_role(UserRole.AUDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    query = db.query(Lender)
    needle = _norm(q)
    if needle:
        like = f"%{needle}%"
        query = query.filter((Lender.company_name.ilike(like)) | (Lender.business_number.ilike(like)))
    rows = query.order_by(Lender.company_name.asc()).all()
    return [r.to_dict() for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_lender(
    body: LenderCreateRequest,
    _: User = Depends(require_role(UserRole.AUDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    business_number = _norm(body.business_number)
    if business_number and db.query(Lender).filter(Lender.business_number == business_number).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 등록된 사업자번호입니다.")
    row = Lender(
        company_name=_norm(body.company_name),
        business_number=business_number,
        ceo_name=_norm(body.ceo_name),
        credit_score_nice=body.credit_score_nice,
        credit_score_kcb=body.credit_score_kcb,
        direct_debt=body.direct_debt,
        guarantee_debt=body.guarantee_debt,
        financial_data=[f.model_dump() for f in body.financial_data] if body.financial_data else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.to_dict()


@router.put("/{lender_id}")
def update_lender(
    lender_id: int,
    body: LenderUpdateRequest,
    _: User = Depends(require_role(UserRole.AUDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    row = db.query(Lender).filter(Lender.id == lender_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="대부업체를 찾을 수 없습니다.")

    new_business = _norm(body.business_number)
    if new_business and new_business != row.business_number:
        dup = db.query(Lender).filter(
            Lender.business_number == new_business, Lender.id != lender_id,
        ).first()
        if dup:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 등록된 사업자번호입니다.")
        row.business_number = new_business

    if body.company_name is not None:
        norm = _norm(body.company_name)
        if norm:
            row.company_name = norm
    if body.ceo_name is not None:
        row.ceo_name = _norm(body.ceo_name)
    if body.credit_score_nice is not None:
        row.credit_score_nice = body.credit_score_nice
    if body.credit_score_kcb is not None:
        row.credit_score_kcb = body.credit_score_kcb
    if body.direct_debt is not None:
        row.direct_debt = body.direct_debt
    if body.guarantee_debt is not None:
        row.guarantee_debt = body.guarantee_debt
    if body.financial_data is not None:
        row.financial_data = [f.model_dump() for f in body.financial_data]

    db.commit()
    db.refresh(row)
    return row.to_dict()


@router.delete("/{lender_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lender(
    lender_id: int,
    _: User = Depends(require_role(UserRole.AUDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    row = db.query(Lender).filter(Lender.id == lender_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="대부업체를 찾을 수 없습니다.")
    db.delete(row)
    db.commit()
    return None
