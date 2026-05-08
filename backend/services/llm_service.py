"""LLM 호출 추상화 (OpenAI ChatCompletion).

ADR-008. 모델/타임아웃은 settings 에서 주입. 호출 결과를 그대로 반환하며,
재시도·감사 로그·캐싱은 호출자가 책임진다 (감사 로그는 analysis_service에서 처리).
"""
from __future__ import annotations

import logging
from typing import Optional

from openai import OpenAI

from core.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        key = api_key or settings.openai_api_key
        if not key:
            raise ValueError("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
        self._client = OpenAI(api_key=key, timeout=settings.llm_timeout_seconds)
        self.model = model or settings.openai_model
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
