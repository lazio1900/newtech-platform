from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from core.database import Base


class OidcConfig(Base):
    __tablename__ = "oidc_config"

    id = Column(Integer, primary_key=True, index=True)
    issuer = Column(String(500), nullable=False, default="")
    realm = Column(String(200), nullable=False, default="")
    client_id = Column(String(200), nullable=False, default="")
    jwks_url = Column(String(500), nullable=False, default="")
    employee_claim = Column(String(200), nullable=False, default="employee_number")
    roles_claim = Column(String(200), nullable=False, default="realm_access.roles")
    is_active = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
