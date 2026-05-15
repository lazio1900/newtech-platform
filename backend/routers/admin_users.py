"""관리자용 사용자 관리 라우터: /api/admin/users/*.

목록·생성·정보수정(role 포함)·비번 reset·비활성화(soft delete).
모든 endpoint 가 admin role 가드.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.auth import require_role
from core.database import get_db
from models import User, UserRole
from services import user_service

router = APIRouter()


def _user_to_admin_dict(u: User) -> dict:
    """관리자 화면용 — public_dict 보다 풍부한 필드 포함."""
    return {
        "user_id": u.user_id,
        "role": u.role.value if isinstance(u.role, UserRole) else u.role,
        "company_name": u.company_name,
        "ceo_name": u.ceo_name,
        "business_number": u.business_number,
        "phone": u.phone,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if isinstance(u.created_at, datetime) else None,
        "last_login_at": u.last_login_at.isoformat() if isinstance(u.last_login_at, datetime) else None,
    }


class AdminUserCreateRequest(BaseModel):
    user_id: str = Field(..., min_length=3, max_length=80)
    password: str = Field(..., min_length=4, max_length=200)
    role: UserRole = UserRole.CUSTOMER
    company_name: str | None = Field(None, max_length=200)
    ceo_name: str | None = Field(None, max_length=80)
    business_number: str | None = Field(None, max_length=40)
    phone: str | None = Field(None, max_length=40)


class AdminUserUpdateRequest(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None
    company_name: str | None = Field(None, max_length=200)
    ceo_name: str | None = Field(None, max_length=80)
    business_number: str | None = Field(None, max_length=40)
    phone: str | None = Field(None, max_length=40)


class AdminPasswordResetRequest(BaseModel):
    new_password: str = Field(..., min_length=4, max_length=200)


@router.get("")
def list_users(
    search: str | None = Query(None, max_length=120),
    role: UserRole | None = Query(None),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """사용자 목록. user_id / company_name / ceo_name 부분 일치 검색."""
    items, total = user_service.admin_list_users(
        db, search=search, role=role, is_active=is_active,
        page=page, page_size=page_size,
    )
    return {
        "status": "success",
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_user_to_admin_dict(u) for u in items],
    }


@router.post("")
def create_user(
    request: AdminUserCreateRequest,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """사용자 신규 생성 — 관리자가 직접. 초기 비번 부여."""
    try:
        user = user_service.create_user(
            db,
            user_id=request.user_id,
            password=request.password,
            role=request.role,
            company_name=request.company_name,
            ceo_name=request.ceo_name,
            business_number=request.business_number,
            phone=request.phone,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"status": "success", "user": _user_to_admin_dict(user)}


def _get_target_or_404(db: Session, user_id: str) -> User:
    target = user_service.admin_get_user(db, user_id)
    if not target:
        raise HTTPException(status_code=404, detail=f"사용자 '{user_id}' 를 찾을 수 없습니다.")
    return target


@router.get("/{user_id}")
def get_user(
    user_id: str,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    return {"status": "success", "user": _user_to_admin_dict(_get_target_or_404(db, user_id))}


@router.patch("/{user_id}")
def update_user(
    user_id: str,
    request: AdminUserUpdateRequest,
    admin_user: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """사용자 정보 변경 (역할·활성화·프로필). 본인은 본인의 role/is_active 변경 불가."""
    target = _get_target_or_404(db, user_id)
    if target.user_id == admin_user.user_id and (request.role is not None or request.is_active is False):
        raise HTTPException(
            status_code=400,
            detail="본인의 역할 또는 활성 상태는 변경할 수 없습니다.",
        )
    target = user_service.admin_update_user(
        db, target,
        role=request.role,
        is_active=request.is_active,
        company_name=request.company_name,
        ceo_name=request.ceo_name,
        business_number=request.business_number,
        phone=request.phone,
    )
    return {"status": "success", "user": _user_to_admin_dict(target)}


@router.post("/{user_id}/password-reset")
def reset_password(
    user_id: str,
    request: AdminPasswordResetRequest,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """관리자 임의 비번 reset."""
    target = _get_target_or_404(db, user_id)
    try:
        user_service.admin_reset_password(db, target, request.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success"}


@router.delete("/{user_id}")
def delete_user(
    user_id: str,
    admin_user: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """사용자 비활성화 (soft delete — is_active=False). 본인 삭제 금지."""
    target = _get_target_or_404(db, user_id)
    if target.user_id == admin_user.user_id:
        raise HTTPException(status_code=400, detail="본인 계정은 비활성화할 수 없습니다.")
    user_service.admin_soft_delete(db, target)
    return {"status": "success"}
