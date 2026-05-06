"""단지별 주변 시설 (read-only).

newtech_data 가 채우는 collector 테이블. 본 앱은 분석 시 입지점수 산출에 활용.
"""
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from core.database import Base


class ComplexFacility(Base):
    __tablename__ = "complex_facilities"

    id = Column(Integer, primary_key=True, index=True)
    complex_id = Column(Integer, ForeignKey("complexes.id"), nullable=False)

    facility_type = Column(String(20), nullable=False, comment="school/subway/hospital/cctv/ev_charger ...")
    sub_type = Column(String(40), nullable=True, comment="kindergarten/elementary/middle/high 등")

    external_id = Column(String(80), nullable=True)
    name = Column(String(200), nullable=False)
    address = Column(String(500), nullable=True)
    phone = Column(String(40), nullable=True)

    distance_m = Column(Integer, nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)

    meta = Column(JSONB, nullable=True)

    fetched_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    complex = relationship("Complex")

    __table_args__ = (
        UniqueConstraint("complex_id", "facility_type", "external_id", name="uq_facility_complex_type_extid"),
        Index("ix_facility_complex_type", "complex_id", "facility_type"),
    )
