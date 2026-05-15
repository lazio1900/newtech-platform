"""LLM 시스템 프롬프트 registry + DB override.

- PROMPT_REGISTRY: 각 feature 와 사용 가능한 prompt key 메타정보 (UI 노출용)
- get_prompt(feature, key, default): DB row 있으면 content, 없으면 default 반환
- set_prompt / reset_prompt: admin 편집·복원
- list_prompts: admin UI 목록
"""
from typing import Optional, TypedDict

from sqlalchemy.orm import Session

from models import LlmPrompt


class PromptKeyMeta(TypedDict):
    label: str
    description: str


class FeatureMeta(TypedDict):
    label: str
    description: str
    prompts: dict[str, PromptKeyMeta]


# 각 AI 서비스의 편집 가능한 시스템 프롬프트 목록.
# user_prompt 는 코드에서 데이터로 동적 구성되므로 편집 대상 아님.
PROMPT_REGISTRY: dict[str, FeatureMeta] = {
    "property": {
        "label": "입지 분석",
        "description": "단지 위치·주변 시설(학군/지하철/병원/공원) 점수 기반 자연어 분석",
        "prompts": {
            "system": {
                "label": "시스템 프롬프트",
                "description": "LLM 역할·출력 형식(JSON)·작성 규칙 정의",
            },
        },
    },
    "market": {
        "label": "시세 분석",
        "description": "KB 시세 · 실거래가 · 매물 호가 종합 자연어 분석",
        "prompts": {
            "system": {
                "label": "시스템 프롬프트",
                "description": "LLM 역할·출력 형식(JSON)·작성 규칙",
            },
        },
    },
    "nearby": {
        "label": "유사물건 분석",
        "description": "인근 유사 단지 + 평단가 추이 기반 종합 코멘트",
        "prompts": {
            "system": {
                "label": "시스템 프롬프트",
                "description": "도메인 판단 기준 · 평단가 비교 규칙 · 출력 형식",
            },
        },
    },
    "overall": {
        "label": "종합 의견 / 심사 권고",
        "description": "위 분석 결과 통합 → 담보 적정성 종합 코멘트 + 심사 권고",
        "prompts": {
            "system": {
                "label": "시스템 프롬프트",
                "description": "심사역 관점의 종합 의견 작성 가이드",
            },
        },
    },
    "rights": {
        "label": "등기부 권리 분석",
        "description": "MinerU markdown 등기부 → 권리 JSON 추출 (소유권/근저당/전세권/말소 처리)",
        "prompts": {
            "system": {
                "label": "시스템 프롬프트",
                "description": "1차 추출 — JSON 스키마 · 말소사항 처리 · 요약 페이지 SSOT",
            },
            "critique": {
                "label": "검증 프롬프트",
                "description": "1차 결과 자기검증 — 누락/오류/환각 issue 리스트 생성",
            },
        },
    },
}


def get_prompt(db: Session, feature_key: str, prompt_key: str, default: str) -> str:
    """DB override 우선, 없으면 default 반환. 모든 LLM 호출이 이 함수를 통해 system prompt 획득."""
    row = (
        db.query(LlmPrompt)
        .filter(LlmPrompt.feature_key == feature_key, LlmPrompt.prompt_key == prompt_key)
        .first()
    )
    if row and row.content:
        return row.content
    return default


def list_prompts(db: Session) -> list[dict]:
    """admin UI 용 — registry 의 모든 feature/key 조합에 대해 default 와 override 정보 반환."""
    rows = db.query(LlmPrompt).all()
    by_key = {(r.feature_key, r.prompt_key): r for r in rows}

    items = []
    for fkey, fmeta in PROMPT_REGISTRY.items():
        for pkey, pmeta in fmeta["prompts"].items():
            row = by_key.get((fkey, pkey))
            items.append({
                "feature_key": fkey,
                "feature_label": fmeta["label"],
                "feature_description": fmeta["description"],
                "prompt_key": pkey,
                "prompt_label": pmeta["label"],
                "prompt_description": pmeta["description"],
                "has_override": row is not None,
                "content": row.content if row else None,  # DB content (override 가 있을 때만)
                "updated_at": row.updated_at.isoformat() if row else None,
                "updated_by": row.updated_by if row else None,
            })
    return items


def set_prompt(
    db: Session, feature_key: str, prompt_key: str, content: str, updated_by: Optional[str]
) -> LlmPrompt:
    """upsert. 같은 (feature, key) 가 있으면 content 갱신, 없으면 신규."""
    _ensure_known_key(feature_key, prompt_key)
    row = (
        db.query(LlmPrompt)
        .filter(LlmPrompt.feature_key == feature_key, LlmPrompt.prompt_key == prompt_key)
        .first()
    )
    if row:
        row.content = content
        row.updated_by = updated_by
    else:
        row = LlmPrompt(
            feature_key=feature_key,
            prompt_key=prompt_key,
            content=content,
            updated_by=updated_by,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def reset_prompt(db: Session, feature_key: str, prompt_key: str) -> bool:
    """DB override 삭제 → 다음 호출부터 default 사용. 삭제 성공 여부 반환."""
    _ensure_known_key(feature_key, prompt_key)
    row = (
        db.query(LlmPrompt)
        .filter(LlmPrompt.feature_key == feature_key, LlmPrompt.prompt_key == prompt_key)
        .first()
    )
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def _ensure_known_key(feature_key: str, prompt_key: str) -> None:
    feat = PROMPT_REGISTRY.get(feature_key)
    if not feat or prompt_key not in feat["prompts"]:
        raise ValueError(f"unknown feature/key: {feature_key}/{prompt_key}")
