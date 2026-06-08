"""운영 전환 체크리스트 라우터: /api/admin/migration/*.

사내망 운영 전환에 필요한 사전 조건을 한 화면으로 확인. 각 항목은 자동 검증이
가능한 것만 포함하고, 실패 시 어드민 페이지로 deep-link 안내.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.auth import require_role
from core.config import settings
from core.database import get_db
from models import DbConnection, DataSourceMapping, User, UserRole
from services import db_connection_service, entity_registry, data_source_mapping_service

router = APIRouter()


def _check_db_connections(db: Session) -> dict:
    """사내망 DB 연결 — Oracle 연결이 한 개 이상 + 테스트 성공."""
    oracle_conns = (
        db.query(DbConnection)
        .filter(DbConnection.driver == "oracle", DbConnection.is_active.is_(True))
        .all()
    )
    if not oracle_conns:
        return {
            "key": "db_connections",
            "label": "사내망 Oracle 연결",
            "ok": False,
            "detail": "활성 Oracle 연결이 없습니다.",
            "link": "/admin/db-connections",
        }
    failed = []
    for c in oracle_conns:
        r = db_connection_service.test_connection(c)
        if not r.get("ok"):
            failed.append(f"{c.name}: {r.get('error')}")
    if failed:
        return {
            "key": "db_connections",
            "label": "사내망 Oracle 연결",
            "ok": False,
            "detail": "연결 테스트 실패: " + " / ".join(failed),
            "link": "/admin/db-connections",
        }
    return {
        "key": "db_connections",
        "label": "사내망 Oracle 연결",
        "ok": True,
        "detail": f"{len(oracle_conns)}개 연결 모두 정상.",
        "link": "/admin/db-connections",
    }


def _check_mappings(db: Session) -> dict:
    """5개 표준 entity 각각에 활성 매핑 한 개 이상."""
    required = set(entity_registry.ENTITY_REGISTRY.keys())
    rows = db.query(DataSourceMapping).filter(DataSourceMapping.is_active.is_(True)).all()
    have = {r.logical_entity for r in rows}
    missing = sorted(required - have)
    if missing:
        return {
            "key": "mappings",
            "label": f"표준 entity 매핑 ({len(required) - len(missing)}/{len(required)})",
            "ok": False,
            "detail": f"매핑 누락: {', '.join(missing)}",
            "link": "/admin/data-mappings",
        }
    # 필드 매핑이 비어있는 row 가 있는지 체크
    empty = []
    for r in rows:
        fm = data_source_mapping_service.parse_field_mappings(r)
        if not fm:
            empty.append(r.logical_entity)
    if empty:
        return {
            "key": "mappings",
            "label": "표준 entity 매핑",
            "ok": False,
            "detail": f"필드 매핑이 비어 있음: {', '.join(empty)}",
            "link": "/admin/data-mappings",
        }
    return {
        "key": "mappings",
        "label": f"표준 entity 매핑 ({len(required)}/{len(required)})",
        "ok": True,
        "detail": "5개 entity 모두 매핑 정의 완료.",
        "link": "/admin/data-mappings",
    }


def _check_app_migration(db: Session) -> dict:
    """우리 앱 소유 DB(Postgres) 의 alembic head 확인."""
    try:
        cur = db.execute(text("SELECT version_num FROM alembic_version_app LIMIT 1"))
        head = cur.scalar()
    except Exception as e:
        return {
            "key": "app_migration",
            "label": "앱 마이그레이션",
            "ok": False,
            "detail": f"alembic 버전 조회 실패: {type(e).__name__}",
            "link": None,
        }
    if not head:
        return {
            "key": "app_migration",
            "label": "앱 마이그레이션",
            "ok": False,
            "detail": "alembic_version_app row 가 없습니다.",
            "link": None,
        }
    return {
        "key": "app_migration",
        "label": "앱 마이그레이션",
        "ok": True,
        "detail": f"현재 head: {head}",
        "link": None,
    }


def _check_data_source_mode() -> dict:
    """데이터 소스 모드 — dev(외부 크롤/PDF 정형화) / prod(폐쇄망 Oracle+수집기).

    운영(ENVIRONMENT=production)인데 dev/pdf 로 남아 있으면 .env 전환 누락 → ok=False.
    dev 환경에선 정보 표시(ok=True). 전환 절차는 mode-switch 런북.
    """
    mode = settings.data_mode
    src = settings.registry_source
    detail = f"현재 모드: {mode} · 등기부 읽기(registry_source): {src}"
    if settings.is_production and not (mode == "prod" and src == "db"):
        return {
            "key": "data_source_mode",
            "label": "데이터 소스 모드",
            "ok": False,
            "detail": detail + " — 운영인데 dev/pdf 잔존(.env 누락: DATA_MODE=prod, REGISTRY_SOURCE=db)",
            "link": None,
        }
    return {
        "key": "data_source_mode",
        "label": "데이터 소스 모드",
        "ok": True,
        "detail": detail,
        "link": None,
    }


def _check_oracle_driver() -> dict:
    try:
        import oracledb  # noqa: F401
    except ImportError:
        return {
            "key": "oracle_driver",
            "label": "Oracle 드라이버",
            "ok": False,
            "detail": "oracledb 미설치 — backend 이미지 rebuild 필요.",
            "link": None,
        }
    return {
        "key": "oracle_driver",
        "label": "Oracle 드라이버",
        "ok": True,
        "detail": "oracledb 사용 가능 (thin mode).",
        "link": None,
    }


@router.get("/checklist")
def get_checklist(
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """운영 전환 체크리스트 — 각 항목 자동 검증 결과."""
    items = [
        _check_oracle_driver(),
        _check_db_connections(db),
        _check_mappings(db),
        _check_app_migration(db),
        _check_data_source_mode(),
    ]
    all_ok = all(it["ok"] for it in items)
    return {"status": "success", "all_ok": all_ok, "items": items}
