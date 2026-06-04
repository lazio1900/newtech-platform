"""관리자용 LLM 프롬프트 편집 라우터: /api/admin/llm/prompts/*.

PROMPT_REGISTRY 의 모든 기능·프롬프트 키 조합을 노출. 각 조합은 (feature, prompt) 당
여러 버전(version, is_active) 로 관리되며, 활성 버전 1개가 LLM 호출에 사용된다.
"""
import time
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


class PromptTestPayload(BaseModel):
    content: str = Field(..., min_length=1, description="테스트할 system prompt 본문")
    user_input: str = Field(..., min_length=1, description="user role 로 들어갈 샘플 입력")
    json_mode: bool = False


def _default_for(feature_key: str, prompt_key: str) -> Optional[str]:
    """코드의 default 상수를 조회. UI 에서 '기본값 보기' / 'reset' 시 사용."""
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
    """모든 feature x prompt_key 의 활성 버전 + default content."""
    items = prompt_registry.list_prompts(db)
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
    """단일 프롬프트의 활성 버전 + default."""
    default_content = _default_for(feature_key, prompt_key)
    if default_content is None:
        raise HTTPException(status_code=404, detail=f"unknown feature/key: {feature_key}/{prompt_key}")
    items = prompt_registry.list_prompts(db)
    target = next((i for i in items if i["feature_key"] == feature_key and i["prompt_key"] == prompt_key), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"unknown feature/key: {feature_key}/{prompt_key}")
    target["default_content"] = default_content
    return {"status": "success", "prompt": target}


@router.get("/{feature_key}/{prompt_key}/samples")
def list_samples(
    feature_key: str,
    prompt_key: str,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """해당 (feature, prompt) 에 미리 정의된 테스트 샘플 목록."""
    from utils.prompt_samples import list_samples as _samples
    return {"status": "success", "samples": _samples(feature_key, prompt_key)}


@router.get("/{feature_key}/{prompt_key}/versions")
def list_versions(
    feature_key: str,
    prompt_key: str,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """해당 (feature, prompt) 의 전체 버전 이력."""
    try:
        rows = prompt_registry.list_versions(db, feature_key, prompt_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "versions": rows}


@router.post("")
def upsert_prompt(
    payload: PromptUpsertPayload,
    admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """새 버전으로 저장 — 이전 활성 row 는 자동 비활성화."""
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
    return {"status": "success", "prompt": row.to_dict()}


@router.post("/{feature_key}/{prompt_key}/activate/{version}")
def activate_version(
    feature_key: str,
    prompt_key: str,
    version: int,
    admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """과거 버전 활성화 — 롤백 용도."""
    try:
        row = prompt_registry.activate_version(db, feature_key, prompt_key, version, admin.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not row:
        raise HTTPException(status_code=404, detail=f"version not found: {version}")
    return {"status": "success", "prompt": row.to_dict()}


@router.post("/test")
def test_prompt(
    payload: PromptTestPayload,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """프롬프트 adhoc 테스트 — 저장하지 않고 LLM 호출. 응답·레이턴시·토큰 반환."""
    from services.llm_service import LLMClient
    try:
        client = LLMClient()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    start = time.perf_counter()
    try:
        result = client.complete(payload.user_input, system=payload.content, json_mode=payload.json_mode)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM 호출 실패: {e}")
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return {
        "status": "success",
        "elapsed_ms": elapsed_ms,
        "model": result.get("model"),
        "text": result.get("text"),
        "prompt_tokens": result.get("prompt_tokens"),
        "completion_tokens": result.get("completion_tokens"),
        "finish_reason": result.get("finish_reason"),
    }


@router.delete("/{feature_key}/{prompt_key}")
def reset_prompt(
    feature_key: str,
    prompt_key: str,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """활성 버전 비활성화 — 다음 호출부터 default 사용. 과거 버전은 보존."""
    try:
        removed = prompt_registry.reset_prompt(db, feature_key, prompt_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "removed": removed}
