"""Oracle→PG ETL 관리: /api/admin/oracle-etl/*

운영 현장 튜닝을 UI로: 테이블/컬럼 매핑 조회·수정, Oracle 실제 스키마 probe(autofill),
동기화(미러) 실행. 연결은 관리자 등록 Oracle DbConnection(driver='oracle') 사용.
"""
import json
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth import require_role
from core.database import get_db
from models import OracleEtlMapping, User, UserRole
from services import oracle_etl_service

router = APIRouter()


class MappingUpdate(BaseModel):
    oracle_table: Optional[str] = None
    column_overrides: Optional[Dict[str, str]] = None  # {pg_col: oracle_col} — 다른 것만
    enabled: Optional[bool] = None


@router.get("/mappings")
def list_mappings(
    _: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """12개 내부 테이블 매핑(코드 기본 + DB 오버라이드 병합)."""
    return {
        "mappings": [
            {
                "internal_table": s["internal_table"],
                "oracle_table": s["oracle_table"],
                "default_oracle_table": s["default_oracle_table"],
                "columns": [{"pg": pg, "oracle": oc} for pg, oc in s["columns"]],
                "column_overrides": s["column_overrides"],
                "enabled": s["enabled"],
            }
            for s in oracle_etl_service.resolve_mappings(db)
        ]
    }


@router.put("/mappings/{internal_table}")
def update_mapping(
    internal_table: str,
    body: MappingUpdate,
    _: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """한 내부 테이블의 Oracle 물리명/컬럼 오버라이드/활성 수정."""
    if internal_table not in oracle_etl_service._MODEL_BY_TABLE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="알 수 없는 내부 테이블")
    row = (
        db.query(OracleEtlMapping)
        .filter(OracleEtlMapping.internal_table == internal_table)
        .first()
    )
    if not row:
        default = next(ot for m, ot in oracle_etl_service.TABLE_MAP if m.__tablename__ == internal_table)
        row = OracleEtlMapping(internal_table=internal_table, oracle_table=default)
        db.add(row)
    if body.oracle_table:
        row.oracle_table = body.oracle_table
    if body.column_overrides is not None:
        row.column_overrides = (
            json.dumps(body.column_overrides, ensure_ascii=False) if body.column_overrides else None
        )
    if body.enabled is not None:
        row.enabled = body.enabled
    db.commit()
    return {"status": "success", "internal_table": internal_table}


@router.get("/probe")
def probe_oracle(
    _: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """Oracle 실제 테이블/컬럼 목록 — 매핑 autofill 보조."""
    try:
        return oracle_etl_service.probe(db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Oracle probe 실패: {type(e).__name__}: {str(e)[:200]}",
        )


@router.post("/run")
def run_sync(
    _: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """Oracle→PG 미러 동기화 실행(테이블별 결과 반환)."""
    try:
        return oracle_etl_service.run_etl(db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ETL 실행 실패: {type(e).__name__}: {str(e)[:200]}",
        )
