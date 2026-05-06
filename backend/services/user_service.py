"""User CRUD + 인증 (DB 기반, Phase 1b)."""
from datetime import datetime
from typing import Optional

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
