"""관리자용 LLM 프롬프트 편집 라우터: /api/admin/llm/prompts/*.

PROMPT_REGISTRY 의 모든 기능·프롬프트 키 조합을 노출하고, 각각에 대해
DB override 를 set/reset 할 수 있다. 빈 override → 코드 default 사용.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.auth import require_role
from core.database import get_db
from models import User, UserRole
from services import prompt_registry

router = APIRouter()


class PromptUpsertPayload(BaseModel):
    feature_key: str = Field(..., max_length=60)
    prompt_key: str = Field(..., max_length=40)
    content: str = Field(..., min_length=1)


def _default_for(feature_key: str, prompt_key: str) -> Optional[str]:
    """코드의 default 상수를 조회. UI 에서 '기본값 보기' / 'reset' 시 사용."""
    # 각 서비스의 default constant 를 동적으로 import. 모듈명·constant 명 매핑.
    mapping = {
        ("property", "system"): ("services.ai_property_analysis_service", "SYSTEM_PROMPT"),
        ("market",   "system"): ("services.ai_market_analysis_service",   "SYSTEM_PROMPT"),
        ("nearby",   "system"): ("services.ai_nearby_analysis_service",   "SYSTEM_PROMPT"),
        ("overall",  "system"): ("services.ai_overall_analysis_service",  "SYSTEM_PROMPT"),
        ("rights",   "system"): ("services.ai_rights_analysis_service",   "SYSTEM_PROMPT"),
        ("rights",   "critique"): ("services.ai_rights_analysis_service", "CRITIQUE_PROMPT"),
    }
    pair = mapping.get((feature_key, prompt_key))
    if not pair:
        return None
    module_name, const_name = pair
    import importlib
    try:
        mod = importlib.import_module(module_name)
        return getattr(mod, const_name, None)
    except Exception:
        return None


@router.get("")
def list_prompts(
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """모든 feature x prompt_key 의 메타 + override 상태."""
    items = prompt_registry.list_prompts(db)
    # default content 도 함께 노출 (UI 에서 비교·복원 가능)
    for it in items:
        it["default_content"] = _default_for(it["feature_key"], it["prompt_key"])
    return {"status": "success", "items": items}


@router.get("/{feature_key}/{prompt_key}")
def get_prompt(
    feature_key: str,
    prompt_key: str,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """단일 프롬프트 — override + default."""
    default_content = _default_for(feature_key, prompt_key)
    if default_content is None:
        raise HTTPException(status_code=404, detail=f"unknown feature/key: {feature_key}/{prompt_key}")
    items = prompt_registry.list_prompts(db)
    target = next((i for i in items if i["feature_key"] == feature_key and i["prompt_key"] == prompt_key), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"unknown feature/key: {feature_key}/{prompt_key}")
    target["default_content"] = default_content
    return {"status": "success", "prompt": target}


@router.post("")
def upsert_prompt(
    payload: PromptUpsertPayload,
    admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """프롬프트 override 저장 (upsert). 다음 LLM 호출부터 적용."""
    try:
        row = prompt_registry.set_prompt(
            db,
            feature_key=payload.feature_key,
            prompt_key=payload.prompt_key,
            content=payload.content,
            updated_by=admin.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "status": "success",
        "prompt": {
            "feature_key": row.feature_key,
            "prompt_key": row.prompt_key,
            "content": row.content,
            "updated_at": row.updated_at.isoformat(),
            "updated_by": row.updated_by,
        },
    }


@router.delete("/{feature_key}/{prompt_key}")
def reset_prompt(
    feature_key: str,
    prompt_key: str,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """override 삭제 — 다음 호출부터 default 사용."""
    try:
        removed = prompt_registry.reset_prompt(db, feature_key, prompt_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "removed": removed}
