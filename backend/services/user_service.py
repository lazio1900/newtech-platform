"""User CRUD + 인증 (DB 기반, Phase 1b)."""
from datetime import datetime
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.security import hash_password, verify_password
from models import User, UserRole


def get_by_user_id(db: Session, user_id: str) -> Optional[User]:
    return db.query(User).filter(User.user_id == user_id).first()


def create_user(
    db: Session,
    *,
    user_id: str,
    password: str,
    role: UserRole = UserRole.CUSTOMER,
    company_name: str | None = None,
    ceo_name: str | None = None,
    business_number: str | None = None,
    phone: str | None = None,
) -> User:
    """사용자 생성. user_id 중복 시 ValueError."""
    if get_by_user_id(db, user_id):
        raise ValueError(f"user_id already exists: {user_id}")

    user = User(
        user_id=user_id,
        password_hash=hash_password(password),
        role=role,
        company_name=company_name,
        ceo_name=ceo_name,
        business_number=business_number,
        phone=phone,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, user_id: str, password: str) -> Optional[User]:
    user = get_by_user_id(db, user_id)
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def mark_login(db: Session, user: User) -> None:
    user.last_login_at = datetime.utcnow()
    db.commit()


# ----- 본인 셀프 서비스 -----

def update_profile(
    db: Session,
    user: User,
    *,
    company_name: Optional[str] = None,
    ceo_name: Optional[str] = None,
    business_number: Optional[str] = None,
    phone: Optional[str] = None,
) -> User:
    """본인 프로필 수정. None 인 필드는 변경하지 않음 (PATCH 의미)."""
    if company_name is not None:
        user.company_name = company_name
    if ceo_name is not None:
        user.ceo_name = ceo_name
    if business_number is not None:
        user.business_number = business_number
    if phone is not None:
        user.phone = phone
    db.commit()
    db.refresh(user)
    return user


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    """본인 비번 변경. 현재 비번 검증 실패 시 ValueError, 길이 부족 시 ValueError."""
    if not verify_password(current_password, user.password_hash):
        raise ValueError("현재 비밀번호가 일치하지 않습니다.")
    if not new_password or len(new_password) < 4:
        raise ValueError("새 비밀번호는 4자 이상이어야 합니다.")
    user.password_hash = hash_password(new_password)
    db.commit()


# ----- 관리자용 CRUD -----

def admin_list_users(
    db: Session,
    *,
    search: Optional[str] = None,
    role: Optional[UserRole] = None,
    is_active: Optional[bool] = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[User], int]:
    """사용자 목록 + 총 건수. user_id / company_name / ceo_name 부분 일치."""
    q = db.query(User)
    if search:
        kw = f"%{search.strip()}%"
        q = q.filter(or_(
            User.user_id.ilike(kw),
            User.company_name.ilike(kw),
            User.ceo_name.ilike(kw),
        ))
    if role is not None:
        q = q.filter(User.role == role)
    if is_active is not None:
        q = q.filter(User.is_active == is_active)
    total = q.count()
    items = (
        q.order_by(User.created_at.desc())
        .offset(max(0, (page - 1) * page_size))
        .limit(max(1, min(page_size, 200)))
        .all()
    )
    return items, total


def admin_get_user(db: Session, target_user_id: str) -> Optional[User]:
    return get_by_user_id(db, target_user_id)


def admin_update_user(
    db: Session,
    target: User,
    *,
    role: Optional[UserRole] = None,
    is_active: Optional[bool] = None,
    company_name: Optional[str] = None,
    ceo_name: Optional[str] = None,
    business_number: Optional[str] = None,
    phone: Optional[str] = None,
) -> User:
    """관리자 사용자 정보 변경. None 인 필드는 그대로 둠."""
    if role is not None:
        target.role = role
    if is_active is not None:
        target.is_active = is_active
    if company_name is not None:
        target.company_name = company_name
    if ceo_name is not None:
        target.ceo_name = ceo_name
    if business_number is not None:
        target.business_number = business_number
    if phone is not None:
        target.phone = phone
    db.commit()
    db.refresh(target)
    return target


def admin_reset_password(db: Session, target: User, new_password: str) -> None:
    """관리자 임의 비번 reset. 현재 비번 확인 없이 덮어씀."""
    if not new_password or len(new_password) < 4:
        raise ValueError("비밀번호는 4자 이상이어야 합니다.")
    target.password_hash = hash_password(new_password)
    db.commit()


def admin_soft_delete(db: Session, target: User) -> None:
    """삭제 대신 is_active=False 로 비활성화. 데이터 무결성 보존 (FK 참조 보호)."""
    target.is_active = False
    db.commit()
