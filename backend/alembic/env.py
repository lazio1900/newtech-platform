"""Alembic 환경 설정.

ADR-002에 따라 본 앱 소유 테이블만 마이그레이션 대상으로 한다.
수집기(별도 프로젝트)가 소유한 테이블은 autogenerate 비교에서 제외한다.
"""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# backend/ 를 sys.path에 추가 (alembic 실행 위치가 backend/)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings  # noqa: E402
from models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata

# 수집기(별도 프로젝트)가 소유 — 본 앱은 read-only로 사용. autogenerate 제외.
COLLECTOR_TABLES = {
    "complexes",
    "areas",
    "kb_prices",
    "transactions",
    "listings",
    "complex_facilities",
    "crawl_jobs",
    "crawl_runs",
    "crawl_tasks",
    "raw_payloads",
}


def include_object(object, name, type_, reflected, compare_to) -> bool:
    if type_ == "table" and name in COLLECTOR_TABLES:
        return False
    if type_ == "column" and getattr(object.table, "name", None) in COLLECTOR_TABLES:
        return False
    return True


# 본 앱은 newtech_data와 같은 DB를 공유 (ADR-002 / INTEGRATION.md).
# 두 프로젝트의 alembic 충돌을 막기 위해 본 앱은 자체 version_table 사용.
# newtech_data 는 default(`alembic_version`)를 그대로 사용한다.
APP_VERSION_TABLE = "alembic_version_app"


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
        version_table=APP_VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
            version_table=APP_VERSION_TABLE,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
