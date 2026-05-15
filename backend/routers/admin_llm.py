"""관리자용 LLM 연결 관리 라우터: /api/admin/llm/connections/*.

- 목록·생성·수정·삭제
- 기본(default) 연결 지정
- 테스트 호출 (간단한 ping)
모든 endpoint admin role 가드.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.auth import require_role
from core.database import get_db
from models import LlmConnection, User, UserRole
from services import llm_connection_service

router = APIRouter()


def _mask_api_key(key: Optional[str]) -> Optional[str]:
    """UI 표시용 — 앞 3자 + 끝 3자만, 사이는 ********."""
    if not key:
        return None
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:3]}...{key[-3:]}"


def _to_dict(c: LlmConnection) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "provider": c.provider,
        "base_url": c.base_url,
        "api_key_masked": _mask_api_key(c.api_key),
        "has_api_key": bool(c.api_key),
        "default_model": c.default_model,
        "is_active": c.is_active,
        "is_default": c.is_default,
        "created_at": c.created_at.isoformat() if isinstance(c.created_at, datetime) else None,
        "updated_at": c.updated_at.isoformat() if isinstance(c.updated_at, datetime) else None,
    }


class LlmConnCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    provider: str = Field("openai", max_length=50)
    base_url: Optional[str] = Field(None, max_length=500)
    api_key: Optional[str] = Field(None, max_length=500)
    default_model: str = Field(..., min_length=1, max_length=200)
    is_active: bool = True
    set_default: bool = False


class LlmConnUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    provider: Optional[str] = Field(None, max_length=50)
    base_url: Optional[str] = Field(None, max_length=500)
    api_key: Optional[str] = Field(None, max_length=500)  # 빈 값 → 미변경
    default_model: Optional[str] = Field(None, max_length=200)
    is_active: Optional[bool] = None


@router.get("")
def list_connections(
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    items = llm_connection_service.list_connections(db)
    return {"status": "success", "items": [_to_dict(c) for c in items]}


@router.post("")
def create_connection(
    payload: LlmConnCreate,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    conn = llm_connection_service.create_connection(
        db,
        name=payload.name,
        provider=payload.provider,
        base_url=payload.base_url,
        api_key=payload.api_key,
        default_model=payload.default_model,
        is_active=payload.is_active,
        set_default=payload.set_default,
    )
    return {"status": "success", "connection": _to_dict(conn)}


def _get_or_404(db: Session, conn_id: int) -> LlmConnection:
    conn = llm_connection_service.get_connection(db, conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"연결 id={conn_id} 를 찾을 수 없습니다.")
    return conn


@router.get("/{conn_id}")
def get_connection(
    conn_id: int,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    return {"status": "success", "connection": _to_dict(_get_or_404(db, conn_id))}


@router.patch("/{conn_id}")
def update_connection(
    conn_id: int,
    payload: LlmConnUpdate,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    conn = _get_or_404(db, conn_id)
    conn = llm_connection_service.update_connection(
        db, conn,
        name=payload.name,
        provider=payload.provider,
        base_url=payload.base_url,
        api_key=payload.api_key,
        default_model=payload.default_model,
        is_active=payload.is_active,
    )
    return {"status": "success", "connection": _to_dict(conn)}


@router.delete("/{conn_id}")
def delete_connection(
    conn_id: int,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    conn = _get_or_404(db, conn_id)
    if conn.is_default:
        raise HTTPException(status_code=400, detail="기본 연결은 삭제할 수 없습니다. 다른 연결을 기본으로 변경 후 삭제하세요.")
    llm_connection_service.delete_connection(db, conn)
    return {"status": "success"}


@router.post("/{conn_id}/set-default")
def set_default(
    conn_id: int,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    conn = llm_connection_service.set_default_connection(db, conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"연결 id={conn_id} 를 찾을 수 없습니다.")
    return {"status": "success", "connection": _to_dict(conn)}


@router.post("/{conn_id}/test")
def test_connection(
    conn_id: int,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """간단한 chat completion 1회 시도. 성공/실패 정보 반환."""
    conn = _get_or_404(db, conn_id)
    result = llm_connection_service.test_connection(conn)
    return {"status": "success", **result}
