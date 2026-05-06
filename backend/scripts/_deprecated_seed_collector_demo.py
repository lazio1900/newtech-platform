"""수집기 영역 데모 데이터 시드 (개발용, ADR-002).

시드된 모니터링/신청건의 주소가 분석 시 실제 단지·시세 데이터와 매칭되도록
8개 단지 + 평형 + 12개월 KB 시세 + 실거래·매물 일부를 적재.

사전 조건: `init_collector_schema.py` 로 수집기 테이블이 존재해야 함.

사용법:
    cd backend
    python scripts/seed_collector_demo.py
"""
from __future__ import annotations

import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dateutil.relativedelta import relativedelta
from sqlalchemy import select

from core.config import settings
from core.database import SessionLocal
from models import (
    Area,
    Complex,
    KBPrice,
    Listing,
    ListingStatus,
    PriorityLevel,
    Transaction,
)


# (이름, 주소, 시군구코드+동코드(10자리), KB ID, 세대수, 준공년도, 복도타입,
#  [(전용㎡, 공급㎡, 평수), ...], 84㎡ 기준 일반시세 베이스(원))
COMPLEXES_SPEC = [
    ("은마아파트",         "서울시 강남구 대치동",       "1168010600", "4083",   4424, 1979, "복도식",
        [(76.79, 102.0, 23), (84.43, 112.0, 25)],   2_550_000_000),
    ("아크로리버파크",     "서울시 서초구 반포동",       "1165010500", "30580",  1612, 2016, "혼합식",
        [(84.97, 113.0, 25), (117.74, 158.0, 35)],  4_500_000_000),
    ("잠실엘스",           "서울시 송파구 잠실동",       "1171010100", "18156",  5678, 2008, "혼합식",
        [(84.80, 113.0, 25), (119.93, 161.0, 36)],  2_400_000_000),
    ("타워팰리스 2차",     "서울시 강남구 도곡동",       "1168011000", "100",     813, 2003, "복도식",
        [(137.41, 175.0, 41), (244.66, 313.0, 73)], 3_900_000_000),
    ("한남더힐",           "서울시 용산구 한남동",       "1117010500", "102036",  600, 2011, "복도식",
        [(84.18, 119.0, 25), (240.30, 332.0, 72)],  6_500_000_000),
    ("마포래미안푸르지오", "서울시 마포구 아현동",       "1144010100", "109208", 3885, 2014, "복도식",
        [(59.92, 84.0, 18),  (84.59, 114.0, 25)],   1_550_000_000),
    ("옥수리버뷰",         "서울시 성동구 옥수동",       "1120010300", "7501",   1199, 2014, "혼합식",
        [(59.89, 80.0, 18),  (84.84, 113.0, 25)],   1_400_000_000),
    ("목동신시가지",       "서울시 양천구 목동",         "1147010100", "4011",  12000, 1986, "복도식",
        [(65.61, 87.0, 19),  (99.71, 130.0, 30)],   1_500_000_000),
]


# 평형별 시세 배수 (84㎡=1.0 기준 단순 보정)
def price_for_area(base_84: int, exclusive_m2: float) -> int:
    return int(base_84 * (exclusive_m2 / 84.0))


def seed_complex(db, spec) -> Complex:
    """단지 1개 + 평형 + 12개월 KB 시세 + 실거래·매물 시드."""
    name, addr, region_code, kb_id, units, build_year, corridor, areas_spec, base_price_84 = spec

    existing = db.query(Complex).filter(Complex.name == name).first()
    if existing:
        print(f"[seed_collector_demo] skip (exists): {name}")
        return existing

    complex_obj = Complex(
        name=name,
        address=addr,
        region_code=region_code,
        kb_complex_id=kb_id,
        priority=PriorityLevel.NORMAL,
        is_active=True,
        collect_listings=True,
        total_households=units,
        corridor_type=corridor,
        build_year=build_year,
    )
    db.add(complex_obj)
    db.flush()

    rng = random.Random(complex_obj.id * 7919)  # 단지별 deterministic
    today = date.today()
    fetched_now = datetime.utcnow()

    for exclusive, supply, pyeong in areas_spec:
        area = Area(
            complex_id=complex_obj.id,
            exclusive_m2=exclusive,
            supply_m2=supply,
            pyeong=pyeong,
            kb_area_code=f"{int(exclusive):03d}A",
        )
        db.add(area)
        db.flush()

        base_price = price_for_area(base_price_84, exclusive)

        # 12개월 월별 KB 시세 — 약간의 트렌드 + 노이즈
        for months_ago in range(11, -1, -1):
            as_of = today.replace(day=1) - relativedelta(months=months_ago)
            # 트렌드: 12개월간 -2% ~ +5% 사이로 단지별 다르게
            trend_pct = (rng.random() * 0.07 - 0.02) * (11 - months_ago) / 11
            noise_pct = (rng.random() - 0.5) * 0.02
            general = int(base_price * (1 + trend_pct + noise_pct))
            spread = int(base_price * 0.05)

            db.add(KBPrice(
                complex_id=complex_obj.id,
                area_id=area.id,
                as_of_date=as_of,
                general_price=general,
                high_avg_price=general + spread,
                low_avg_price=general - spread,
                source="kb",
                fetched_at=fetched_now,
                parser_version="seed-1.0",
            ))

        # 실거래 — 최근 90일 내 4~7건. unique(complex,date,price,m2,floor) 충돌 방지로 set 사용
        n_txn = rng.randint(4, 7)
        seen_keys = set()
        attempts = 0
        while len(seen_keys) < n_txn and attempts < 50:
            attempts += 1
            days_ago = rng.randint(1, 90)
            ctx_date = today - timedelta(days=days_ago)
            floor = rng.randint(2, 25)
            txn_price = int(base_price * (1 + (rng.random() - 0.5) * 0.06))
            key = (ctx_date, txn_price, floor)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            db.add(Transaction(
                complex_id=complex_obj.id,
                contract_date=ctx_date,
                price=txn_price,
                exclusive_m2=exclusive,
                floor=floor,
                reported_date=ctx_date + timedelta(days=rng.randint(1, 14)),
                is_cancelled=False,
                source="molit",
                fetched_at=fetched_now,
            ))

        # 매물 — 5~9건 ACTIVE
        n_lst = rng.randint(5, 9)
        for k in range(n_lst):
            ask = int(base_price * (1 + (rng.random() * 0.05)))
            posted = fetched_now - timedelta(days=rng.randint(1, 60))
            db.add(Listing(
                complex_id=complex_obj.id,
                source_listing_id=f"seed-{complex_obj.id}-{area.id}-{k}",
                ask_price=ask,
                exclusive_m2=exclusive,
                floor=rng.randint(2, 25),
                status=ListingStatus.ACTIVE,
                posted_at=posted,
                status_updated_at=posted,
                source="kb",
                fetched_at=fetched_now,
                last_seen_at=fetched_now,
            ))

    db.commit()
    print(f"[seed_collector_demo] created: {name} "
          f"(areas={len(areas_spec)}, ~12mo prices+txns+listings)")
    return complex_obj


def main() -> int:
    if settings.is_production:
        print("[seed_collector_demo] ERROR: production 환경에서는 실행 금지", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        for spec in COMPLEXES_SPEC:
            seed_complex(db, spec)
    finally:
        db.close()
    print(f"[seed_collector_demo] done. complexes seeded: {len(COMPLEXES_SPEC)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
