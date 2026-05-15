"""DB 연결 설정 — 관리자가 admin panel 에서 여러 endpoint 등록·테스트.

실제 backend 가 사용하는 DATABASE_URL 은 .env 의 settings 가 기동 시점에 로드.
이 테이블의 row 들은 운영 참고·기록·테스트용. is_default 표시는 다음 재시작 시
backend 가 우선 시도할 수 있도록 신호 (현재는 표시만, hot-swap 안 함).
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from core.database import Base


class DbConnection(Base):
    __tablename__ = "db_connections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, comment="UI 표시명")
    driver = Column(String(40), nullable=False, default="postgresql", comment="postgresql 만 우선 지원")
    host = Column(String(200), nullable=False)
    port = Column(Integer, nullable=False, default=5432)
    database = Column(String(120), nullable=False)
    username = Column(String(120), nullable=False)
    password = Column(String(500), nullable=True, comment="평문 저장 (사내·폐쇄망 가정)")
    is_active = Column(Boolean, nullable=False, default=True)
    is_default = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
