from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from .db import Base


class RegistryRequest(Base):
    __tablename__ = "registry_request"
    __table_args__ = (
        UniqueConstraint(
            "address_norm", "type", "issued_date",
            name="uq_registry_address_type_date",
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ic_id = Column(Integer, unique=True, nullable=True)
    address = Column(Text, nullable=False)
    dong = Column(Text)
    ho = Column(Text)
    type = Column(Text, nullable=False, default="집합건물")
    address_norm = Column(Text, nullable=False)
    issued_date = Column(Date, nullable=False)
    status = Column(Text, nullable=False)
    pdf_path = Column(Text)
    cost = Column(Integer, default=0)
    apick_pl_id = Column(Integer)
    requester_id = Column(Text)
    listing_id = Column(Text)
    error_message = Column(Text)
    markdown = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
