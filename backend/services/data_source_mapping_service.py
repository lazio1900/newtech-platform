"""DataSourceMapping CRUD + 검증."""
import json
from typing import Optional

from sqlalchemy.orm import Session

from models import DataSourceMapping
from services.entity_registry import ENTITY_REGISTRY, TRANSFORM_REGISTRY


def list_mappings(db: Session) -> list[DataSourceMapping]:
    return db.query(DataSourceMapping).order_by(DataSourceMapping.id.asc()).all()


def get_mapping(db: Session, mapping_id: int) -> Optional[DataSourceMapping]:
    return db.query(DataSourceMapping).filter(DataSourceMapping.id == mapping_id).first()


def _validate(logical_entity: str, field_mappings: dict) -> None:
    """logical_entity 와 field_mappings 의 구조 검증.

    - logical_entity 가 registry 에 있어야 함
    - field_mappings 의 key 는 entity 의 표준 필드 중 하나
    - 각 value 는 {source_field: str, transform?: str}
    - transform 은 TRANSFORM_REGISTRY 안의 key
    """
    meta = ENTITY_REGISTRY.get(logical_entity)
    if not meta:
        raise ValueError(f"unknown logical_entity: {logical_entity}")
    valid_fields = {f["key"] for f in meta["fields"]}
    valid_transforms = {t["key"] for t in TRANSFORM_REGISTRY}
    for k, v in field_mappings.items():
        if k not in valid_fields:
            raise ValueError(f"'{logical_entity}' 에 없는 필드: {k}")
        if not isinstance(v, dict) or not v.get("source_field"):
            raise ValueError(f"필드 '{k}' 매핑에 source_field 가 없습니다.")
        t = v.get("transform")
        if t and t not in valid_transforms:
            raise ValueError(f"필드 '{k}' 의 transform '{t}' 은 지원되지 않습니다.")


def create_mapping(
    db: Session,
    *,
    name: str,
    logical_entity: str,
    source_db_connection_id: int,
    source_table: str,
    field_mappings: dict,
    is_active: bool = True,
    updated_by: Optional[str] = None,
) -> DataSourceMapping:
    _validate(logical_entity, field_mappings)
    row = DataSourceMapping(
        name=name.strip(),
        logical_entity=logical_entity,
        source_db_connection_id=source_db_connection_id,
        source_table=source_table.strip(),
        field_mappings=json.dumps(field_mappings, ensure_ascii=False),
        is_active=is_active,
        updated_by=updated_by,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_mapping(
    db: Session,
    row: DataSourceMapping,
    *,
    name: Optional[str] = None,
    source_table: Optional[str] = None,
    field_mappings: Optional[dict] = None,
    is_active: Optional[bool] = None,
    updated_by: Optional[str] = None,
) -> DataSourceMapping:
    if name is not None:
        row.name = name.strip()
    if source_table is not None:
        row.source_table = source_table.strip()
    if field_mappings is not None:
        _validate(row.logical_entity, field_mappings)
        row.field_mappings = json.dumps(field_mappings, ensure_ascii=False)
    if is_active is not None:
        row.is_active = is_active
    if updated_by is not None:
        row.updated_by = updated_by
    db.commit()
    db.refresh(row)
    return row


def delete_mapping(db: Session, row: DataSourceMapping) -> None:
    db.delete(row)
    db.commit()


def parse_field_mappings(row: DataSourceMapping) -> dict:
    """field_mappings JSON 문자열 → dict."""
    try:
        return json.loads(row.field_mappings or "{}")
    except json.JSONDecodeError:
        return {}
