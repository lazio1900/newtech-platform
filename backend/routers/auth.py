"""인증 라우터: /api/login, /api/register, /api/me"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.config import settings
from core.database import get_db
from core.security import create_access_token
from models import User, UserRole
from services import user_service

router = APIRouter()


class LoginRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=200)


class RegisterRequest(BaseModel):
    user_id: str = Field(..., min_length=3, max_length=80)
    password: str = Field(..., min_length=4, max_length=200)
    company_name: str = Field(..., min_length=1, max_length=200)
    ceo_name: str = Field(..., min_length=1, max_length=80)
    business_number: str = Field(..., min_length=1, max_length=40)
    phone: str = Field(..., min_length=1, max_length=40)


@router.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """로그인. 성공 시 JWT 발급."""
    user = user_service.authenticate(db, request.user_id, request.password)
    if not user:
        # 사용자 존재 여부를 노출하지 않도록 동일 메시지
        return {"status": "error", "message": "아이디 또는 비밀번호가 올바르지 않습니다."}

    user_service.mark_login(db, user)
    role_value = user.role.value if isinstance(user.role, UserRole) else user.role
    token = create_access_token(subject=user.user_id, role=role_value)

    return {
        "status": "success",
        "access_token": token,
        "token_type": "bearer",
        "expires_in_minutes": settings.jwt_access_token_expire_minutes,
        "user": user.to_public_dict(),
    }


@router.post("/register")
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """대부업체 회원가입 (항상 customer 권한)."""
    try:
        user_service.create_user(
            db,
            user_id=request.user_id,
            password=request.password,
            role=UserRole.CUSTOMER,
            company_name=request.company_name,
            ceo_name=request.ceo_name,
            business_number=request.business_number,
            phone=request.phone,
        )
    except ValueError:
        return {"status": "error", "message": "이미 존재하는 아이디입니다."}
    return {"status": "success", "message": "회원가입이 완료되었습니다."}


@router.get("/me")
def get_me(user: User = Depends(get_current_user)):
    """현재 토큰 소유 사용자 정보."""
    return {"status": "success", "user": user.to_public_dict()}
