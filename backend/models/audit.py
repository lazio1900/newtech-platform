import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from core.database import Base


class SearchField(str, enum.Enum):
    COMPANY = "company"
    ADDRESS = "address"


class SearchHistory(Base):
    """자동완성을 위한 검색 이력.

    field+value 조합으로 dedup. 검색될 때마다 count 증가.
    """
    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, index=True)
    field = Column(Enum(SearchField), nullable=False)
    value = Column(String(500), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, comment="검색한 사용자")
    count = Column(Integer, nullable=False, default=1)
    last_searched_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("field", "value", name="uq_search_history_field_value"),
        Index("ix_search_history_field_value", "field", "value"),
    )


class AnalysisAuditLog(Base):
    """AI 분석 호출 감사 로그 (ADR-008, ADR-010).

    분쟁 시 입력/모델/응답을 추적할 수 있도록 영속화. 보존 5년.
    """
    __tablename__ = "analysis_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # 입력 스냅샷
    company_name = Column(String(200), nullable=False)
    property_address = Column(String(500), nullable=False)
    loan_amount = Column(BigInteger, nullable=False)

    # 모델/호출 메타 (OpenAI 등 호출 모델 식별자)
    llm_model = Column(String(80), nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # 결과
    success = Column(Boolean, nullable=False, default=False)
    response_summary = Column(Text, nullable=True, comment="종합의견 텍스트")
    response_full = Column(Text, nullable=True, comment="전체 응답 JSON")
    error_type = Column(String(80), nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
