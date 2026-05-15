"""LLM 연결 설정 — 관리자가 admin panel 에서 등록·관리.

OpenAI 호환 endpoint 만 지원 (Azure OpenAI / vLLM / 자체 호스팅 포함).
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from core.database import Base


class LlmConnection(Base):
    __tablename__ = "llm_connections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, comment="UI 표시명")
    # 현재는 'openai' 만. 향후 'anthropic', 'ollama' 등 확장 여지.
    provider = Column(String(50), nullable=False, default="openai")
    base_url = Column(String(500), nullable=True, comment="null=OpenAI 기본 endpoint")
    api_key = Column(String(500), nullable=True, comment="평문 저장 (사내·폐쇄망 가정)")
    default_model = Column(String(200), nullable=False, comment="이 연결의 기본 모델")
    is_active = Column(Boolean, nullable=False, default=True)
    is_default = Column(Boolean, nullable=False, default=False, comment="LLMClient 가 사용하는 기본 연결")

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
