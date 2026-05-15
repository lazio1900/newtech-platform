"""관리자용 DB 연결 관리 라우터: /api/admin/db/connections/*.

실제 backend 가 사용하는 DATABASE_URL 은 .env 기반. 이 라우터는 endpoint 목록
관리·테스트만 담당. hot-swap 안 함 — 재시작 시점에만 반영됨 (UI 노트).
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.auth import require_role
from core.database import get_db
from models import DbConnection, User, UserRole
from services import db_connection_service

router = APIRouter()


def _mask_password(pw: Optional[str]) -> Optional[str]:
    if not pw:
        return None
    if len(pw) <= 4:
        return "*" * len(pw)
    return f"{pw[:1]}***{pw[-1:]}"


def _to_dict(c: DbConnection) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "driver": c.driver,
        "host": c.host,
        "port": c.port,
        "database": c.database,
        "username": c.username,
        "password_masked": _mask_password(c.password),
        "has_password": bool(c.password),
        "is_active": c.is_active,
        "is_default": c.is_default,
        "created_at": c.created_at.isoformat() if isinstance(c.created_at, datetime) else None,
        "updated_at": c.updated_at.isoformat() if isinstance(c.updated_at, datetime) else None,
    }


class DbConnCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    driver: str = Field("postgresql", max_length=40)
    host: str = Field(..., min_length=1, max_length=200)
    port: int = Field(5432, ge=1, le=65535)
    database: str = Field(..., min_length=1, max_length=120)
    username: str = Field(..., min_length=1, max_length=120)
    password: Optional[str] = Field(None, max_length=500)
    is_active: bool = True
    set_default: bool = False


class DbConnUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    driver: Optional[str] = Field(None, max_length=40)
    host: Optional[str] = Field(None, max_length=200)
    port: Optional[int] = Field(None, ge=1, le=65535)
    database: Optional[str] = Field(None, max_length=120)
    username: Optional[str] = Field(None, max_length=120)
    password: Optional[str] = Field(None, max_length=500)  # 빈 값 → 미변경
    is_active: Optional[bool] = None


@router.get("")
def list_connections(
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    items = db_connection_service.list_connections(db)
    return {"status": "success", "items": [_to_dict(c) for c in items]}


@router.post("")
def create_connection(
    payload: DbConnCreate,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    conn = db_connection_service.create_connection(
        db,
        name=payload.name,
        driver=payload.driver,
        host=payload.host,
        port=payload.port,
        database=payload.database,
        username=payload.username,
        password=payload.password,
        is_active=payload.is_active,
        set_default=payload.set_default,
    )
    return {"status": "success", "connection": _to_dict(conn)}


def _get_or_404(db: Session, conn_id: int) -> DbConnection:
    conn = db_connection_service.get_connection(db, conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"연결 id={conn_id} 를 찾을 수 없습니다.")
    return conn


@router.patch("/{conn_id}")
def update_connection(
    conn_id: int,
    payload: DbConnUpdate,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    conn = _get_or_404(db, conn_id)
    conn = db_connection_service.update_connection(
        db, conn,
        name=payload.name,
        driver=payload.driver,
        host=payload.host,
        port=payload.port,
        database=payload.database,
        username=payload.username,
        password=payload.password,
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
    db_connection_service.delete_connection(db, conn)
    return {"status": "success"}


@router.post("/{conn_id}/set-default")
def set_default(
    conn_id: int,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    conn = db_connection_service.set_default_connection(db, conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"연결 id={conn_id} 를 찾을 수 없습니다.")
    return {"status": "success", "connection": _to_dict(conn)}


@router.post("/{conn_id}/test")
def test_connection(
    conn_id: int,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """간단한 SELECT 1 호출. 성공/실패 정보 반환."""
    conn = _get_or_404(db, conn_id)
    return {"status": "success", **db_connection_service.test_connection(conn)}
