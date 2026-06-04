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


class MappingPreviewRequest(BaseModel):
    limit: int = Field(5, ge=1, le=50)


@router.post("/{mapping_id}/preview")
def preview_mapping(
    mapping_id: int,
    payload: MappingPreviewRequest,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """매핑 정의된 외부 테이블에서 N rows SELECT 후 transform 적용 결과 반환.

    안전상 컬럼/테이블 이름은 영숫자·_·. 만 허용 (식별자 화이트리스트).
    """
    import re
    from services import db_connection_service
    from services.data_transforms import apply as tx_apply

    row = _get_or_404(db, mapping_id)
    fm = data_source_mapping_service.parse_field_mappings(row)
    if not fm:
        raise HTTPException(status_code=400, detail="매핑된 필드가 없습니다.")

    conn = db_connection_service.get_connection(db, row.source_db_connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="연결된 DB 연결이 없습니다.")

    safe_ident = re.compile(r"^[A-Za-z0-9_.]+$")
    if not safe_ident.match(row.source_table):
        raise HTTPException(status_code=400, detail=f"안전하지 않은 테이블명: {row.source_table}")

    columns: list[str] = []
    target_to_source: dict[str, str] = {}
    target_to_transform: dict[str, str] = {}
    for target, m in fm.items():
        sf = (m or {}).get("source_field")
        if not sf:
            continue
        if not safe_ident.match(sf):
            raise HTTPException(status_code=400, detail=f"안전하지 않은 컬럼명: {sf}")
        if sf not in columns:
            columns.append(sf)
        target_to_source[target] = sf
        target_to_transform[target] = (m or {}).get("transform") or "none"

    if not columns:
        raise HTTPException(status_code=400, detail="source_field 가 정의된 필드가 없습니다.")

    cols_sql = ", ".join(columns)
    if conn.driver == "oracle":
        sql = f"SELECT {cols_sql} FROM {row.source_table} FETCH FIRST {payload.limit} ROWS ONLY"
    else:
        sql = f"SELECT {cols_sql} FROM {row.source_table} LIMIT {payload.limit}"

    try:
        db_conn = db_connection_service.open_raw_connection(conn)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"외부 DB 연결 실패: {type(e).__name__}: {e}")

    try:
        cur = db_conn.cursor()
        try:
            cur.execute(sql)
            raw_rows = cur.fetchall()
        finally:
            cur.close()
    except Exception as e:
        return {
            "status": "error",
            "sql": sql,
            "error": f"{type(e).__name__}: {str(e)[:300]}",
        }
    finally:
        try:
            db_conn.close()
        except Exception:
            pass

    def jsonify(v):
        from datetime import date as _d, datetime as _dt
        from decimal import Decimal
        if v is None or isinstance(v, (str, int, float, bool)):
            return v
        if isinstance(v, (_d, _dt)):
            return v.isoformat()
        if isinstance(v, Decimal):
            return float(v)
        return str(v)

    raw_dicts = []
    transformed = []
    for r in raw_rows:
        rd = {col: jsonify(r[i]) for i, col in enumerate(columns)}
        raw_dicts.append(rd)
        td = {target: jsonify(tx_apply(target_to_transform[target], rd[source]))
              for target, source in target_to_source.items()}
        transformed.append(td)

    return {
        "status": "success",
        "sql": sql,
        "columns": columns,
        "raw_rows": raw_dicts,
        "transformed": transformed,
    }
