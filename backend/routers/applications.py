"""대출 신청 라우터: /api/applications/*"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.auth import get_current_user, require_role
from core.database import get_db
from models import (
    APPLICATION_STATUS_LABELS,
    ApplicationStatus,
    User,
    UserRole,
)
from services import application_service

router = APIRouter()


class ApplicationCreateRequest(BaseModel):
    """신청자는 토큰의 사용자로 결정 (body의 applicant_id는 무시)."""
    company_name: str = Field(..., min_length=1, max_length=200)
    ceo_name: str = Field(..., min_length=1, max_length=80)
    property_address: str = Field(..., min_length=1, max_length=500)
    loan_amount: int = Field(..., gt=0)
    loan_duration: int = Field(12, ge=1, le=600)

    # 단지/평형 매칭 (선택). 단지 검색 결과를 선택하지 않은 경우 None 허용.
    complex_id: int | None = None
    complex_name: str | None = Field(None, max_length=200)
    area_id: int | None = None
    exclusive_m2: float | None = None
    pyeong: int | None = Field(None, ge=1, le=300)
    dong: str | None = Field(None, max_length=40)
    ho: str | None = Field(None, max_length=40)


class ApplicationStatusUpdateRequest(BaseModel):
    status: ApplicationStatus
    memo: str | None = Field(None, max_length=2000)


@router.post("")
def submit(
    request: ApplicationCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    app = application_service.submit(
        db,
        applicant=user,
        company_name=request.company_name,
        ceo_name=request.ceo_name,
        property_address=request.property_address,
        loan_amount=request.loan_amount,
        loan_duration=request.loan_duration,
        complex_id=request.complex_id,
        complex_name=request.complex_name,
        area_id=request.area_id,
        exclusive_m2=request.exclusive_m2,
        pyeong=request.pyeong,
        dong=request.dong,
        ho=request.ho,
    )
    return {"status": "success", "application": app.to_dict()}


@router.get("")
def list_applications(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """customer는 자기 신청만, auditor/admin은 전체."""
    role_value = user.role.value if isinstance(user.role, UserRole) else user.role
    if role_value == UserRole.CUSTOMER.value:
        apps = application_service.list_for_applicant(db, user.id)
    else:
        apps = application_service.list_all(db)
    return [a.to_dict() for a in apps]


@router.get("/status-options")
def status_options():
    """상태 드롭다운 메타."""
    return [
        {"value": s.value, "label": APPLICATION_STATUS_LABELS[s]}
        for s in ApplicationStatus
    ]


@router.put("/{app_id}/status")
def update_status(
    app_id: str,
    body: ApplicationStatusUpdateRequest,
    auditor: User = Depends(require_role(UserRole.AUDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    try:
        result = application_service.update_status(
            db,
            app_id=app_id,
            new_status=body.status,
            auditor=auditor,
            memo=body.memo,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="신청건을 찾을 수 없습니다.")
    return {"status": "success", "application": result.to_dict()}
