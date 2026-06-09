"""[dev] 정보계 Oracle 시뮬레이터 구축 — 로컬 oracle 컨테이너에 CCTR_*/CUWT_NIC_* 물리 테이블
생성 + 현재 PG 내부형식 데이터로 시드. 운영엔 실제 정보계가 이 역할을 하므로 **dev 전용**.

이게 #1 운영 ETL(oracle_to_pg_etl)이 읽어들일 "Oracle 쪽" 데이터를 만든다. 즉 흐름:
  크롤/PDF → (이미) PG 내부형식 → [이 스크립트] Oracle 적재 → [oracle_to_pg_etl] Oracle→PG 미러
실행: docker compose --profile oracle 로 oracle 기동 후
  docker compose exec backend python scripts/oracle_sim_setup.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings  # noqa: E402
from core.database import SessionLocal  # noqa: E402
from scripts.internal_oracle_common import (  # noqa: E402
    TABLE_MAP, connect_oracle, mirror_columns, oracle_type,
)


def main() -> None:
    if settings.data_mode != "dev":
        print("거부: dev 전용(로컬 Oracle 시뮬레이터). 운영 정보계엔 실행 금지.", file=sys.stderr)
        sys.exit(2)

    ora = connect_oracle()
    cur = ora.cursor()
    db = SessionLocal()
    try:
        for model, otable in TABLE_MAP:
            cols = mirror_columns(model)
            try:
                cur.execute(f"DROP TABLE {otable} PURGE")
            except Exception:
                pass
            coldefs = ", ".join(
                f"{c.upper()} {oracle_type(model.__table__.columns[c])}" for c in cols
            )
            cur.execute(f"CREATE TABLE {otable} ({coldefs})")

            rows = db.query(model).all()
            if rows:
                placeholders = ", ".join(f":{i + 1}" for i in range(len(cols)))
                colnames = ", ".join(c.upper() for c in cols)
                data = [[getattr(r, c) for c in cols] for r in rows]
                cur.executemany(
                    f"INSERT INTO {otable} ({colnames}) VALUES ({placeholders})", data
                )
            ora.commit()
            print(f"  {otable}: {len(rows)} rows")
    finally:
        db.close()
        cur.close()
        ora.close()
    print("Oracle 시뮬레이터 구축 완료.")


if __name__ == "__main__":
    main()
