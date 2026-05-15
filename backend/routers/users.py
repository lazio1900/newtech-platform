"""사용자 본인 셀프 서비스 라우터: /api/me/* (프로필 수정·비번 변경).

목록·생성·역할 변경 같은 관리자 CRUD 는 routers/admin_users.py 에 분리.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.database import get_db
from models import User
from services import user_service

router = APIRouter()


class MeUpdateRequest(BaseModel):
    company_name: str | None = Field(None, max_length=200)
    ceo_name: str | None = Field(None, max_length=80)
    business_number: str | None = Field(None, max_length=40)
    phone: str | None = Field(None, max_length=40)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=200)
    new_password: str = Field(..., min_length=4, max_length=200)


@router.patch("")
def update_me(
    request: MeUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """본인 프로필 수정."""
    user_service.update_profile(
        db, user,
        company_name=request.company_name,
        ceo_name=request.ceo_name,
        business_number=request.business_number,
        phone=request.phone,
    )
    return {"status": "success", "user": user.to_public_dict()}


@router.post("/password")
def change_password(
    request: PasswordChangeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """본인 비밀번호 변경."""
    try:
        user_service.change_password(db, user, request.current_password, request.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success"}
