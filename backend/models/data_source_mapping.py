"""외부 데이터 소스 → 본 앱 표준 모델 매핑 정의.

사내 이관 후 외부 DB 의 스키마가 본 앱 모델과 다를 때, 컬럼명·타입 변환 규칙을
admin UI 에서 정의해두면 data_source_adapter 가 그 룰로 데이터를 정규화한다.

field_mappings JSON 예:
  {
    "id":          {"source_field": "apt_id"},
    "name":        {"source_field": "apt_nm"},
    "built_year":  {"source_field": "constr_yyyy", "transform": "to_year_string"},
    ...
  }
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)

from core.database import Base


class DataSourceMapping(Base):
    __tablename__ = "data_source_mappings"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, comment="UI 표시명")
    # 본 앱이 인지하는 표준 엔티티 키 — services.entity_registry 참조
    logical_entity = Column(String(40), nullable=False, comment="복합/평형/실거래/KB시세 등")
    # 어느 외부 DB 에서 읽어올지
    source_db_connection_id = Column(Integer, ForeignKey("db_connections.id"), nullable=False)
    source_table = Column(String(200), nullable=False, comment="외부 DB 의 테이블·뷰명")
    # 표준 필드 → 외부 컬럼·변환 매핑 (JSON 직렬화 텍스트)
    field_mappings = Column(Text, nullable=False, default="{}")
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(80), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "source_db_connection_id", "logical_entity",
            name="uq_data_source_mappings_db_entity",
        ),
        Index("ix_data_source_mappings_entity", "logical_entity"),
    )
