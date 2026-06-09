"""Oracle→PG ETL 테이블/컬럼 매핑 — 관리자가 admin panel 에서 편집.

정보계 실제 물리 테이블/컬럼명이 명세와 다를 때 **코드 수정 없이 UI로 조정**하기 위함.
한 행 = 내부형식 PG 테이블 1개의 Oracle 매핑. 행이 없으면 코드 기본값(명세) 사용.
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from core.database import Base


class OracleEtlMapping(Base):
    __tablename__ = "oracle_etl_mappings"

    id = Column(Integer, primary_key=True, index=True)
    internal_table = Column(String(64), unique=True, nullable=False, comment="PG 내부형식 테이블명 (예: cctr_kb_apt_m)")
    oracle_table = Column(String(128), nullable=False, comment="Oracle 물리 테이블명 (예: CCTR_KB_APT_M)")
    column_overrides = Column(Text, nullable=True, comment='컬럼 오버라이드 JSON {pg_col: oracle_col} — 다른 것만')
    enabled = Column(Boolean, nullable=False, default=True, comment="이 테이블 ETL 포함 여부")

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
