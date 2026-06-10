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
                "label": "시스템 프롬프트 (외부망/주변시설)",
                "description": "LLM 역할·출력 형식(JSON)·작성 규칙 정의",
            },
            "system_internal": {
                "label": "시스템 프롬프트 (내부망/단지특성)",
                "description": "폐쇄망 — 단지 규모·연식·주차·시세 기반 분석 (좌표/시설 없음)",
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


def _get_active(db: Session, feature_key: str, prompt_key: str) -> Optional[LlmPrompt]:
    return (
        db.query(LlmPrompt)
        .filter(
            LlmPrompt.feature_key == feature_key,
            LlmPrompt.prompt_key == prompt_key,
            LlmPrompt.is_active.is_(True),
        )
        .first()
    )


def get_prompt(db: Session, feature_key: str, prompt_key: str, default: str) -> str:
    """활성 버전의 content 반환. 활성 버전이 없으면 default."""
    row = _get_active(db, feature_key, prompt_key)
    if row and row.content:
        return row.content
    return default


def list_prompts(db: Session) -> list[dict]:
    """admin UI 용 — registry 의 모든 feature/key 조합에 대해 활성 버전 정보 반환."""
    items = []
    for fkey, fmeta in PROMPT_REGISTRY.items():
        for pkey, pmeta in fmeta["prompts"].items():
            row = _get_active(db, fkey, pkey)
            items.append({
                "feature_key": fkey,
                "feature_label": fmeta["label"],
                "feature_description": fmeta["description"],
                "prompt_key": pkey,
                "prompt_label": pmeta["label"],
                "prompt_description": pmeta["description"],
                "has_override": row is not None,
                "version": row.version if row else None,
                "content": row.content if row else None,
                "updated_at": row.updated_at.isoformat() if row else None,
                "updated_by": row.updated_by if row else None,
            })
    return items


def list_versions(db: Session, feature_key: str, prompt_key: str) -> list[dict]:
    """해당 (feature, prompt) 의 전체 버전 이력 (최신 version 부터)."""
    _ensure_known_key(feature_key, prompt_key)
    rows = (
        db.query(LlmPrompt)
        .filter(LlmPrompt.feature_key == feature_key, LlmPrompt.prompt_key == prompt_key)
        .order_by(LlmPrompt.version.desc())
        .all()
    )
    return [r.to_dict() for r in rows]


def set_prompt(
    db: Session, feature_key: str, prompt_key: str, content: str, updated_by: Optional[str]
) -> LlmPrompt:
    """새 버전 insert. 같은 (feature, prompt) 의 기존 활성 row 는 비활성화한다."""
    _ensure_known_key(feature_key, prompt_key)

    # 이전 활성 row 비활성화 (partial unique 충돌 방지)
    prev = _get_active(db, feature_key, prompt_key)
    next_version = 1
    if prev:
        prev.is_active = False
        next_version = (prev.version or 0) + 1
        db.flush()

    # 같은 (feature, prompt, version) 행이 이미 있으면 다음 번호로 — 안전장치
    while db.query(LlmPrompt).filter(
        LlmPrompt.feature_key == feature_key,
        LlmPrompt.prompt_key == prompt_key,
        LlmPrompt.version == next_version,
    ).first():
        next_version += 1

    row = LlmPrompt(
        feature_key=feature_key,
        prompt_key=prompt_key,
        version=next_version,
        is_active=True,
        content=content,
        updated_by=updated_by,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def activate_version(
    db: Session, feature_key: str, prompt_key: str, version: int, updated_by: Optional[str]
) -> Optional[LlmPrompt]:
    """지정된 버전을 활성화하고 기존 활성 row 는 비활성화."""
    _ensure_known_key(feature_key, prompt_key)
    target = (
        db.query(LlmPrompt)
        .filter(
            LlmPrompt.feature_key == feature_key,
            LlmPrompt.prompt_key == prompt_key,
            LlmPrompt.version == version,
        )
        .first()
    )
    if not target:
        return None
    if target.is_active:
        return target
    prev = _get_active(db, feature_key, prompt_key)
    if prev and prev.id != target.id:
        prev.is_active = False
        db.flush()
    target.is_active = True
    target.updated_by = updated_by
    db.commit()
    db.refresh(target)
    return target


def reset_prompt(db: Session, feature_key: str, prompt_key: str) -> bool:
    """현재 활성 버전을 비활성화 — 다음 호출부터 default 사용. 과거 버전은 보존."""
    _ensure_known_key(feature_key, prompt_key)
    row = _get_active(db, feature_key, prompt_key)
    if not row:
        return False
    row.is_active = False
    db.commit()
    return True


def _ensure_known_key(feature_key: str, prompt_key: str) -> None:
    feat = PROMPT_REGISTRY.get(feature_key)
    if not feat or prompt_key not in feat["prompts"]:
        raise ValueError(f"unknown feature/key: {feature_key}/{prompt_key}")
