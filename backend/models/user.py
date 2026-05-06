import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String

from core.database import Base


class UserRole(str, enum.Enum):
    """사용자 역할 (ADR-004)"""
    CUSTOMER = "customer"
    AUDITOR = "auditor"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(80), unique=True, nullable=False, index=True, comment="로그인 ID")
    password_hash = Column(String(255), nullable=False, comment="bcrypt 해시")
    role = Column(Enum(UserRole), nullable=False, default=UserRole.CUSTOMER)

    company_name = Column(String(200), nullable=True)
    ceo_name = Column(String(80), nullable=True)
    business_number = Column(String(40), nullable=True)
    phone = Column(String(40), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    def to_public_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "role": self.role.value if isinstance(self.role, UserRole) else self.role,
            "company_name": self.company_name,
            "ceo_name": self.ceo_name,
            "business_number": self.business_number,
            "phone": self.phone,
        }
