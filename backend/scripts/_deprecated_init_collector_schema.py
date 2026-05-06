"""수집기 테이블 임시 부트스트랩 (개발용, ADR-002 / ADR-003).

본 앱 alembic은 본 앱 소유 테이블(users, loan_applications 등)만 관리한다.
수집기(별도 프로젝트 예정) 소유 테이블 — complexes/areas/kb_prices/transactions/
listings/crawl_*/raw_payloads — 은 본 앱이 read-only로 사용한다.

수집기 프로젝트가 아직 분리되기 전이므로, 같은 PostgreSQL에 임시로 테이블만
만들어두는 스크립트. 시드 데이터는 `seed_collector_demo.py`로 별도 적재.
수집기 분리 시 본 스크립트는 폐기 → 수집기 자체 alembic이 인계.

사용법:
    cd backend
    python scripts/init_collector_schema.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect

from core.database import Base, engine
import models  # noqa: F401  (모든 모델을 메타데이터에 등록)


COLLECTOR_TABLES = {
    "complexes",
    "areas",
    "kb_prices",
    "transactions",
    "listings",
    "crawl_jobs",
    "crawl_runs",
    "crawl_tasks",
    "raw_payloads",
}


def main() -> int:
    targets = [
        t for t in Base.metadata.tables.values() if t.name in COLLECTOR_TABLES
    ]
    if not targets:
        print("[init_collector_schema] No collector tables found in metadata.", file=sys.stderr)
        return 1

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())

    to_create = [t for t in targets if t.name not in existing]
    if not to_create:
        print("[init_collector_schema] All collector tables already exist:",
              sorted(t.name for t in targets))
        return 0

    Base.metadata.create_all(bind=engine, tables=to_create)
    print("[init_collector_schema] Created:",
          sorted(t.name for t in to_create))
    return 0


if __name__ == "__main__":
    sys.exit(main())
