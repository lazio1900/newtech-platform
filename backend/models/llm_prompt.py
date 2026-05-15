"""LLM 시스템 프롬프트 override — 관리자가 admin panel 에서 편집.

코드의 기본 상수가 fallback. DB row 가 있으면 그 content 가 우선.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, UniqueConstraint

from core.database import Base


class LlmPrompt(Base):
    __tablename__ = "llm_prompts"

    id = Column(Integer, primary_key=True, index=True)
    feature_key = Column(String(60), nullable=False, comment="기능 식별자 (예: rights, nearby)")
    prompt_key = Column(String(40), nullable=False, comment="프롬프트 종류 (예: system, critique)")
    content = Column(Text, nullable=False)

    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(80), nullable=True, comment="마지막 수정한 user_id")

    __table_args__ = (
        UniqueConstraint("feature_key", "prompt_key", name="uq_llm_prompts_feature_key"),
        Index("ix_llm_prompts_feature_key", "feature_key"),
    )
