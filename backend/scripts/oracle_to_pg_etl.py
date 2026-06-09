"""#1 운영 ETL 실행 (CLI) — services.oracle_etl_service.run_etl 호출.

연결·매핑은 관리자 DB설정(DbConnection oracle / OracleEtlMapping) 우선, 없으면 env/명세 기본.
관리자 패널 "동기화 실행" 버튼과 동일 로직. 실행: docker compose exec backend python scripts/oracle_to_pg_etl.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import SessionLocal  # noqa: E402
from services.oracle_etl_service import run_etl  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        res = run_etl(db)
    finally:
        db.close()
    print(f"source: {res['source']}")
    for t in res["tables"]:
        if t["status"] == "ok":
            print(f"  {t['oracle_table']} → {t['pg_table']}: {t['rows']} rows")
        else:
            print(f"  {t['oracle_table']} → {t['pg_table']}: {t['status']} {t.get('error', '')}")
    print(f"Oracle→PG 미러 완료 (총 {res['total_rows']} rows).")


if __name__ == "__main__":
    main()
