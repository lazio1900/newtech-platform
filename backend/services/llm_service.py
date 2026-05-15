"""LLM 호출 추상화 (OpenAI ChatCompletion).

ADR-008. 호출 결과를 그대로 반환하며, 재시도·감사 로그·캐싱은 호출자가 책임진다.

연결 정보 우선순위:
  1. admin panel 에서 등록한 DB 의 기본(default) LlmConnection
  2. fallback: .env 의 settings.openai_api_key / openai_model
"""
from __future__ import annotations

import logging
from typing import Optional

from openai import OpenAI

from core.config import settings

logger = logging.getLogger(__name__)


def _resolve_connection_params() -> tuple[str, Optional[str], str]:
    """현재 사용할 (api_key, base_url, model) 결정. DB default 우선, 없으면 env fallback."""
    # DB lookup — 실패해도 env 로 폴백
    try:
        from core.database import SessionLocal
        from services.llm_connection_service import get_default_connection
        db = SessionLocal()
        try:
            conn = get_default_connection(db)
        finally:
            db.close()
        if conn and conn.api_key:
            return conn.api_key, conn.base_url, conn.default_model
    except Exception as e:
        logger.warning(f"[llm] DB 기본 연결 조회 실패, env 폴백: {e}")
    return settings.openai_api_key or "", None, settings.openai_model


class LLMClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        db_key, db_base_url, db_model = _resolve_connection_params()
        key = api_key or db_key
        if not key:
            raise ValueError("LLM 연결이 설정되지 않았습니다. 관리자 패널에서 연결을 등록하거나 OPENAI_API_KEY 를 설정하세요.")
        client_kwargs: dict = {"api_key": key, "timeout": settings.llm_timeout_seconds}
        if db_base_url:
            client_kwargs["base_url"] = db_base_url
        self._client = OpenAI(**client_kwargs)
        self.model = model or db_model
        self.max_tokens = settings.llm_max_tokens

    def complete(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        json_mode: bool = False,
    ) -> dict:
        """단일 프롬프트 호출. 응답 텍스트와 사용량 메타를 dict로 반환.

        json_mode=True 일 때 response_format=json_object 로 호출 (system/user에
        'JSON' 단어가 포함되어야 OpenAI가 활성화함).
        """
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        usage = response.usage
        return {
            "text": choice.message.content or "",
            "model": response.model,
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "finish_reason": choice.finish_reason,
        }
