"""LLM 시스템 프롬프트 override — 관리자가 admin panel 에서 편집.

같은 (feature_key, prompt_key) 에 여러 버전이 누적되며, is_active=True 인 row 1개가
실제 LLM 호출에 사용된다. 코드의 기본 상수는 row 가 전혀 없을 때만 fallback.
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint

from core.database import Base


class LlmPrompt(Base):
    __tablename__ = "llm_prompts"

    id = Column(Integer, primary_key=True, index=True)
    feature_key = Column(String(60), nullable=False, comment="기능 식별자 (예: rights, nearby)")
    prompt_key = Column(String(40), nullable=False, comment="프롬프트 종류 (예: system, critique)")
    version = Column(Integer, nullable=False, default=1, comment="해당 (feature, prompt) 의 버전")
    is_active = Column(Boolean, nullable=False, default=True, comment="LLM 호출 시 사용되는 활성 버전 — (feature, prompt) 당 1개")
    content = Column(Text, nullable=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(80), nullable=True, comment="마지막 수정한 user_id")

    __table_args__ = (
        # 같은 (feature, prompt) 에 같은 version 두 번 불가
        UniqueConstraint("feature_key", "prompt_key", "version", name="uq_llm_prompts_fk_pk_ver"),
        # 활성 row 는 (feature, prompt) 당 정확히 1개 — partial index 는 alembic 에서 생성
        Index("ix_llm_prompts_feature_key", "feature_key"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "feature_key": self.feature_key,
            "prompt_key": self.prompt_key,
            "version": self.version,
            "is_active": self.is_active,
            "content": self.content,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M") if self.updated_at else None,
            "updated_by": self.updated_by,
        }
