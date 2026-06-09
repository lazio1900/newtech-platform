"""#1 운영 ETL 코어 — 정보계 Oracle → PG 내부형식 미러. 라우터(admin UI)·스크립트 공용.

연결: 관리자 등록 Oracle DbConnection(driver='oracle') 우선 → 없으면 settings.oracle_*.
매핑: OracleEtlMapping(관리자 편집) 오버레이 → 없으면 코드 기본(명세). 물리명/컬럼이 사내와
달라도 **UI 수정만으로** 대응(코드 불변). 운영 현장 튜닝 최소화가 목표.
"""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal

from sqlalchemy import BigInteger, Float, Integer, String, Text
from sqlalchemy.orm import Session

from core.config import settings
from core.database import engine
from models import internal_kb as ik
from models import registry_nice as rn
from models.db_connection import DbConnection
from models.oracle_etl_mapping import OracleEtlMapping

logger = logging.getLogger(__name__)

# (PG 모델, Oracle 물리 테이블명) 코드 기본 — 사내 명세 기준. UI(OracleEtlMapping)로 오버라이드.
TABLE_MAP = [
    (ik.CctrKbAptM, "CCTR_KB_APT_M"),
    (ik.CctrKbAptPntpI, "CCTR_KB_APT_PNTP_I"),
    (ik.CctrKbAptQtnL, "CCTR_KB_APT_QTN_L"),
    (ik.CctrAptTxcsHist, "CCTR_APT_TXCS_HIST"),
    (ik.CctrKbAptStdngC, "CCTR_KB_APT_STDNG_C"),
    (ik.CctrKbAptTxcsMpngB, "CCTR_KB_APT_TXCS_MPNG_B"),
    (rn.NiceRlesBasic, "CUWT_NIC_RLES_CCRG_M"),
    (rn.NiceRlesBrief, "CUWT_NIC_RLES_BRF_I"),
    (rn.NiceRlesCollateral, "CUWT_NIC_RLES_COLL_I"),
    (rn.NiceRlesDetail, "CUWT_NIC_RLES_CCRG_D"),
    (rn.NiceRlesParty, "CUWT_NIC_RLES_PDL_I"),
    (rn.NiceRlesHeader, "CUWT_NIC_RLES_HDR_D"),
]
_MODEL_BY_TABLE = {m.__tablename__: m for m, _ in TABLE_MAP}


def mirror_columns(model) -> list[str]:
    """미러 대상 PG 컬럼 — surrogate 'id'(Oracle 자연키엔 없음) 제외."""
    return [c.name for c in model.__table__.columns if c.name != "id"]


def oracle_type(col) -> str:
    t = col.type
    if isinstance(t, String):
        return f"VARCHAR2({t.length or 2000} CHAR)"
    if isinstance(t, BigInteger):
        return "NUMBER(19)"
    if isinstance(t, Integer):
        return "NUMBER(10)"
    if isinstance(t, Float):
        return "BINARY_DOUBLE"
    if isinstance(t, Text):
        return "CLOB"
    return "VARCHAR2(4000)"


def _norm(v):
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    return v


# Oracle 식별자 검증 — f-string SQL 조립 전 SQL injection 차단. 테이블은 OWNER.TABLE 허용.
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]*$")
_IDENT_TABLE = re.compile(r"^([A-Za-z_][A-Za-z0-9_$#]*\.)?[A-Za-z_][A-Za-z0-9_$#]*$")


def _safe_table(name: str) -> str:
    if not name or not _IDENT_TABLE.match(name):
        raise ValueError(f"유효하지 않은 Oracle 테이블명: {name!r}")
    return name


def _safe_col(name: str) -> str:
    if not name or not _IDENT.match(name):
        raise ValueError(f"유효하지 않은 Oracle 컬럼명: {name!r}")
    return name


def connect_oracle(db: Session):
    """Oracle thin connect — 관리자 DbConnection(oracle) 우선, 없으면 settings.oracle_*."""
    import oracledb
    oracledb.defaults.fetch_lobs = False

    conn = (
        db.query(DbConnection)
        .filter(DbConnection.driver == "oracle", DbConnection.is_active.is_(True))
        .order_by(DbConnection.is_default.desc(), DbConnection.id.asc())
        .first()
    )
    if conn:
        dsn = f"{conn.host}:{conn.port or 1521}/{conn.database}"
        return oracledb.connect(user=conn.username, password=conn.password or "",
                                dsn=dsn, tcp_connect_timeout=10), f"DbConnection:{conn.name}"
    if settings.oracle_dsn and settings.oracle_user:
        return oracledb.connect(user=settings.oracle_user, password=settings.oracle_password or "",
                                dsn=settings.oracle_dsn, tcp_connect_timeout=10), "env:ORACLE_*"
    raise RuntimeError("Oracle 연결 미설정 — 관리자 패널에서 Oracle 연결 등록(또는 ORACLE_DSN).")


def resolve_mappings(db: Session) -> list[dict]:
    """코드 기본(명세) 위에 OracleEtlMapping(DB) 오버레이. admin 표시 + ETL 공용."""
    overrides = {m.internal_table: m for m in db.query(OracleEtlMapping).all()}
    out = []
    for model, default_otable in TABLE_MAP:
        itable = model.__tablename__
        ov = overrides.get(itable)
        colov = {}
        if ov and ov.column_overrides:
            try:
                colov = json.loads(ov.column_overrides)
            except (ValueError, TypeError):
                colov = {}
        cols = [(pg, colov.get(pg) or pg.upper()) for pg in mirror_columns(model)]
        out.append({
            "model": model,
            "internal_table": itable,
            "oracle_table": (ov.oracle_table if ov else None) or default_otable,
            "default_oracle_table": default_otable,
            "columns": cols,
            "column_overrides": colov,
            "enabled": ov.enabled if ov else True,
        })
    return out


def run_etl(db: Session) -> dict:
    """Oracle → PG 미러 (테이블별 delete→insert). 한 테이블 실패해도 나머지 진행(개별 보고)."""
    conn, source = connect_oracle(db)
    conn.call_timeout = 300_000  # 문장당 5분 — 정체 시 무한 hang 방지
    cur = conn.cursor()
    cur.arraysize = 5000  # 스트리밍 fetch 배치
    tables, total = [], 0
    try:
        for spec in resolve_mappings(db):
            model, otable, cols = spec["model"], spec["oracle_table"], spec["columns"]
            if not spec["enabled"]:
                tables.append({"pg_table": model.__tablename__, "oracle_table": otable, "status": "skipped"})
                continue
            try:
                model.__table__.create(engine, checkfirst=True)
                # 식별자 검증(SQL injection 차단) 후 조립
                safe_table = _safe_table(otable)
                safe_cols = [_safe_col(oc) for _, oc in cols]
                pg_cols = [pg for pg, _ in cols]
                db.query(model).delete()
                cur.execute(f"SELECT {', '.join(safe_cols)} FROM {safe_table}")
                n = 0
                for row in cur:  # fetchall 대신 스트리밍 + 주기적 flush/expunge 로 메모리 바운드
                    db.add(model(**{pg_cols[i]: _norm(row[i]) for i in range(len(pg_cols))}))
                    n += 1
                    if n % 5000 == 0:
                        db.flush()
                        db.expunge_all()
                db.commit()  # delete+insert 단일 트랜잭션(테이블별 원자적)
                total += n
                tables.append({"pg_table": model.__tablename__, "oracle_table": otable, "status": "ok", "rows": n})
            except Exception as e:
                db.rollback()
                tables.append({"pg_table": model.__tablename__, "oracle_table": otable,
                               "status": "error", "error": f"{type(e).__name__}: {str(e)[:200]}"})
    finally:
        cur.close()
        conn.close()
    return {"source": source, "total_rows": total, "tables": tables}


def probe(db: Session) -> dict:
    """Oracle 실제 테이블/컬럼 목록 — 매핑 작성 보조(현장 autofill)."""
    # 시스템 스키마 제외 — 접속계정 소유(USER_*) + SELECT 권한 있는 타 스키마(ALL_*) 모두.
    sys_owners = ("SYS", "SYSTEM", "XDB", "MDSYS", "CTXSYS", "DBSNMP", "OUTLN", "WMSYS",
                  "APPQOSSYS", "DVSYS", "AUDSYS", "LBACSYS", "OJVMSYS", "ORDSYS", "ORDDATA",
                  "GSMADMIN_INTERNAL", "REMOTE_SCHEDULER_AGENT", "DBSFWUSER")
    not_in = ", ".join(f"'{o}'" for o in sys_owners)
    conn, source = connect_oracle(db)
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT owner, table_name FROM all_tables WHERE owner NOT IN ({not_in}) ORDER BY owner, table_name")
        rows = cur.fetchall()
        # 접속계정 소유는 bare 이름, 그 외는 OWNER.TABLE (매핑에 그대로 넣을 수 있게)
        me = (conn.username or "").upper()
        all_tables = [t if o == me else f"{o}.{t}" for o, t in rows]
        columns: dict[str, list[str]] = {}
        cur.execute(f"SELECT owner, table_name, column_name FROM all_tab_columns WHERE owner NOT IN ({not_in}) ORDER BY owner, table_name, column_id")
        for owner, tname, cname in cur.fetchall():
            key = tname if owner == me else f"{owner}.{tname}"
            columns.setdefault(key, []).append(cname)
    finally:
        cur.close()
        conn.close()
    return {"source": source, "tables": all_tables, "columns": columns}
