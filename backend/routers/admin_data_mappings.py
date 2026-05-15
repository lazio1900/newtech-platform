"""관리자용 외부 데이터 매핑 라우터: /api/admin/data-mappings/*.

표준 entity / transform 메타정보 + 매핑 CRUD.
admin 가드.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.auth import require_role
from core.database import get_db
from models import DataSourceMapping, User, UserRole
from services import data_source_mapping_service, entity_registry

router = APIRouter()


def _to_dict(row: DataSourceMapping) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "logical_entity": row.logical_entity,
        "source_db_connection_id": row.source_db_connection_id,
        "source_table": row.source_table,
        "field_mappings": data_source_mapping_service.parse_field_mappings(row),
        "is_active": row.is_active,
        "created_at": row.created_at.isoformat() if isinstance(row.created_at, datetime) else None,
        "updated_at": row.updated_at.isoformat() if isinstance(row.updated_at, datetime) else None,
        "updated_by": row.updated_by,
    }


class MappingCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    logical_entity: str = Field(..., max_length=40)
    source_db_connection_id: int
    source_table: str = Field(..., min_length=1, max_length=200)
    field_mappings: dict = Field(default_factory=dict)
    is_active: bool = True


class MappingUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    source_table: Optional[str] = Field(None, max_length=200)
    field_mappings: Optional[dict] = None
    is_active: Optional[bool] = None


@router.get("/registry")
def get_registry(
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """매핑 편집 UI 가 사용하는 메타 — 표준 entity 와 변환 함수 목록."""
    return {
        "status": "success",
        "entities": entity_registry.list_entities(),
        "transforms": entity_registry.list_transforms(),
    }


@router.get("")
def list_mappings(
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    items = data_source_mapping_service.list_mappings(db)
    return {"status": "success", "items": [_to_dict(r) for r in items]}


@router.post("")
def create_mapping(
    payload: MappingCreate,
    admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    try:
        row = data_source_mapping_service.create_mapping(
            db,
            name=payload.name,
            logical_entity=payload.logical_entity,
            source_db_connection_id=payload.source_db_connection_id,
            source_table=payload.source_table,
            field_mappings=payload.field_mappings,
            is_active=payload.is_active,
            updated_by=admin.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "mapping": _to_dict(row)}


def _get_or_404(db: Session, mid: int) -> DataSourceMapping:
    row = data_source_mapping_service.get_mapping(db, mid)
    if not row:
        raise HTTPException(status_code=404, detail=f"매핑 id={mid} 를 찾을 수 없습니다.")
    return row


@router.patch("/{mapping_id}")
def update_mapping(
    mapping_id: int,
    payload: MappingUpdate,
    admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    row = _get_or_404(db, mapping_id)
    try:
        row = data_source_mapping_service.update_mapping(
            db, row,
            name=payload.name,
            source_table=payload.source_table,
            field_mappings=payload.field_mappings,
            is_active=payload.is_active,
            updated_by=admin.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "mapping": _to_dict(row)}


@router.delete("/{mapping_id}")
def delete_mapping(
    mapping_id: int,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    row = _get_or_404(db, mapping_id)
    data_source_mapping_service.delete_mapping(db, row)
    return {"status": "success"}
