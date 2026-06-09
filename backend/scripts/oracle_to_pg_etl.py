"""#1 운영 ETL — 정보계 Oracle(CCTR_*/CUWT_NIC_RLES_*) → PG 내부형식 미러(cctr_*/nice_rles_*).

앱은 INTERNAL_ONLY 로 이 PG 미러를 읽는다(시세=internal_market_service, 등기부=registry_db_service).
**운영 전환 = settings.oracle_dsn/user/password 만 사내 정보계로 교체** — ETL 본체·매핑 불변.
(물리 테이블/컬럼명이 사내와 다르면 internal_oracle_common.TABLE_MAP·컬럼만 조정.)

현재는 전체 미러 재적재(테이블별 delete→insert). 대용량 운영은 워터마크 증분이 후속(step2 §2).
실행: docker compose exec backend python scripts/oracle_to_pg_etl.py
"""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import SessionLocal, engine  # noqa: E402
from scripts.internal_oracle_common import TABLE_MAP, connect_oracle, mirror_columns  # noqa: E402


def _norm(v):
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    return v


def main() -> None:
    ora = connect_oracle()
    cur = ora.cursor()
    db = SessionLocal()
    total = 0
    try:
        for model, otable in TABLE_MAP:
            model.__table__.create(engine, checkfirst=True)
            cols = mirror_columns(model)
            cur.execute(f"SELECT {', '.join(c.upper() for c in cols)} FROM {otable}")
            rows = cur.fetchall()

            db.query(model).delete()  # 전체 미러 재적재
            for row in rows:
                db.add(model(**{cols[i]: _norm(row[i]) for i in range(len(cols))}))
            db.commit()
            total += len(rows)
            print(f"  {otable} → {model.__tablename__}: {len(rows)} rows")
    finally:
        db.close()
        cur.close()
        ora.close()
    print(f"Oracle→PG 미러 완료 (총 {total} rows).")


if __name__ == "__main__":
    main()
