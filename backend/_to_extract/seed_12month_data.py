"""
기존 DB 단지들에 과거 12개월 랜덤 데이터 삽입 스크립트

기능:
  - DB에 등록된 모든 단지(Complex)를 조회
  - 각 단지의 면적(Area)별로 12개월 주간 KB 시세 생성
  - 12개월간 랜덤 실거래 데이터 생성
  - 매물(호가) 데이터 생성

사용법:
    cd backend
    python seed_12month_data.py
"""

import random
from datetime import date, datetime, timedelta

from core.database import SessionLocal, engine
from models import Base
from models.complex import Complex, Area
from models.price_data import KBPrice, Transaction, Listing, ListingStatus


# ── 설정 ─────────────────────────────────────────
MONTHS_BACK = 12
WEEKS_IN_PERIOD = MONTHS_BACK * 4 + 4  # ~52주
KB_TX_PER_COMPLEX = 24       # KB 실거래가 (월 2건)
MOLIT_TX_PER_COMPLEX = 18    # 국토부 실거래가 (월 1.5건)
KB_LISTINGS_PER_COMPLEX = 12   # KB 매물
NAVER_LISTINGS_PER_COMPLEX = 10  # 네이버 부동산 호가

# 면적별 기준 시세 범위 (만원 단위로 설정, 원 단위로 변환)
# 전용면적(㎡)에 따라 기준가 결정
def _base_price_for_area(exclusive_m2: float) -> int:
    """면적에 따른 기준 시세 (원 단위)"""
    if exclusive_m2 < 40:
        return random.randint(30000, 50000) * 10000  # 3~5억
    elif exclusive_m2 < 60:
        return random.randint(50000, 90000) * 10000  # 5~9억
    elif exclusive_m2 < 85:
        return random.randint(80000, 130000) * 10000  # 8~13억
    elif exclusive_m2 < 115:
        return random.randint(110000, 170000) * 10000  # 11~17억
    else:
        return random.randint(150000, 250000) * 10000  # 15~25억


def _generate_price_trend(base_price: int, num_weeks: int) -> list[int]:
    """
    12개월간 주간 시세 추이 생성.
    완만한 상승/하락 트렌드 + 노이즈.
    """
    # 전체 트렌드: -5% ~ +10% 범위에서 랜덤 방향
    total_change_pct = random.uniform(-0.05, 0.10)
    weekly_change = total_change_pct / num_weeks

    prices = []
    current = base_price
    for _ in range(num_weeks):
        # 트렌드 + 주간 노이즈 (±0.5%)
        noise = random.uniform(-0.005, 0.005)
        current = int(current * (1 + weekly_change + noise))
        # 1000만원 단위 반올림
        current = round(current / 10_000_000) * 10_000_000
        prices.append(current)

    return prices


def seed_12month():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # 모든 단지 조회
        complexes = db.query(Complex).all()
        if not complexes:
            print("[WARN] DB에 등록된 단지가 없습니다. 먼저 seed_demo_data.py를 실행하세요.")
            return

        print(f"[INFO] {len(complexes)}개 단지에 12개월 데이터 생성 시작")
        today = date.today()
        now = datetime.utcnow()
        start_date = today - timedelta(days=MONTHS_BACK * 30)

        total_prices = 0
        total_tx = 0
        total_listings = 0

        # 단지 상세 정보 채우기 (없는 경우 랜덤 생성)
        updated_info = 0
        for cx in complexes:
            changed = False
            if not cx.total_households:
                cx.total_households = random.randint(200, 2500)
                changed = True
            if not cx.corridor_type:
                cx.corridor_type = random.choice(["계단식", "복도식", "혼합식"])
                changed = True
            if not cx.build_year:
                cx.build_year = random.randint(1985, 2024)
                changed = True
            if changed:
                updated_info += 1
        if updated_info > 0:
            db.flush()
            print(f"[INFO] {updated_info}개 단지에 세대수/복도타입/연식 랜덤 생성")

        for cx in complexes:
            areas = db.query(Area).filter(Area.complex_id == cx.id).all()

            # 기존 데이터 삭제 (중복 방지)
            db.query(Listing).filter(Listing.complex_id == cx.id).delete()
            db.query(Transaction).filter(Transaction.complex_id == cx.id).delete()
            db.query(KBPrice).filter(KBPrice.complex_id == cx.id).delete()
            db.flush()

            # ── KB 시세 (면적별, 주간) ──
            for area in areas:
                base = _base_price_for_area(area.exclusive_m2)
                gen_prices = _generate_price_trend(base, WEEKS_IN_PERIOD)

                for week_idx, gen_price in enumerate(gen_prices):
                    as_of = start_date + timedelta(weeks=week_idx)
                    if as_of > today:
                        break

                    high_avg = int(gen_price * random.uniform(1.05, 1.10))
                    high_avg = round(high_avg / 10_000_000) * 10_000_000
                    low_avg = int(gen_price * random.uniform(0.90, 0.95))
                    low_avg = round(low_avg / 10_000_000) * 10_000_000

                    db.add(KBPrice(
                        complex_id=cx.id,
                        area_id=area.id,
                        as_of_date=as_of,
                        general_price=gen_price,
                        high_avg_price=high_avg,
                        low_avg_price=low_avg,
                        source="kb",
                        fetched_at=now,
                    ))
                    total_prices += 1

            # ── 면적 선택지 준비 ──
            if not areas:
                area_choices = [{"m2": 84.0, "floor_range": (1, 25)}]
            else:
                area_choices = [
                    {"m2": a.exclusive_m2, "floor_range": (1, 25)}
                    for a in areas
                ]

            # 중복 키 방지용 set: (contract_date, price, exclusive_m2, floor)
            tx_keys_seen: set = set()

            def _add_transactions(count: int, source: str, price_noise: tuple):
                """거래 데이터 생성 공통 함수"""
                added = 0
                for _ in range(count):
                    for _retry in range(10):
                        days_ago = random.randint(1, MONTHS_BACK * 30)
                        contract_dt = today - timedelta(days=days_ago)

                        ac = random.choice(area_choices)
                        m2 = ac["m2"]
                        floor = random.randint(*ac["floor_range"])

                        tx_base = _base_price_for_area(m2)
                        tx_price = int(tx_base * random.uniform(*price_noise))
                        tx_price = round(tx_price / 10_000_000) * 10_000_000

                        key = (contract_dt, tx_price, m2, floor)
                        if key not in tx_keys_seen:
                            tx_keys_seen.add(key)
                            break
                    else:
                        continue

                    # 국토부는 신고일(reported_date) 포함
                    reported = None
                    if source == "molit":
                        reported = contract_dt + timedelta(days=random.randint(7, 45))
                        if reported > today:
                            reported = today

                    db.add(Transaction(
                        complex_id=cx.id,
                        contract_date=contract_dt,
                        price=tx_price,
                        exclusive_m2=m2,
                        floor=floor,
                        reported_date=reported,
                        is_cancelled=random.random() < 0.03,
                        source=source,
                        fetched_at=now,
                    ))
                    added += 1
                return added

            # ── KB 실거래가 ──
            kb_tx = _add_transactions(KB_TX_PER_COMPLEX, "kb", (0.90, 1.10))
            total_tx += kb_tx

            # ── 국토부 실거래가 ──
            molit_tx = _add_transactions(MOLIT_TX_PER_COMPLEX, "molit", (0.88, 1.08))
            total_tx += molit_tx

            # ── 매물/호가 생성 공통 함수 ──
            statuses_active_heavy = (
                [ListingStatus.ACTIVE] * 6
                + [ListingStatus.SOLD] * 4
                + [ListingStatus.REMOVED] * 2
            )
            statuses_sold_heavy = (
                [ListingStatus.ACTIVE] * 3
                + [ListingStatus.SOLD] * 6
                + [ListingStatus.REMOVED] * 3
            )

            def _add_listings(count: int, source: str, id_prefix: str,
                              price_range: tuple, statuses: list):
                """매물 데이터 생성 공통 함수"""
                added = 0
                for li_idx in range(count):
                    ac = random.choice(area_choices)
                    m2 = ac["m2"]
                    floor = random.randint(*ac["floor_range"])
                    status = statuses[li_idx % len(statuses)]

                    ask_base = _base_price_for_area(m2)
                    ask_price = int(ask_base * random.uniform(*price_range))
                    ask_price = round(ask_price / 10_000_000) * 10_000_000

                    if status == ListingStatus.ACTIVE:
                        days_ago = random.randint(1, 30)
                    else:
                        days_ago = random.randint(30, MONTHS_BACK * 30)

                    posted = today - timedelta(days=days_ago)
                    listing_id = f"{id_prefix}-{cx.id:04d}-{li_idx+1:03d}"

                    db.add(Listing(
                        complex_id=cx.id,
                        source_listing_id=listing_id,
                        ask_price=ask_price,
                        exclusive_m2=m2,
                        floor=floor,
                        status=status,
                        posted_at=datetime.combine(posted, datetime.min.time()),
                        source=source,
                        fetched_at=now,
                        last_seen_at=now if status == ListingStatus.ACTIVE else
                            datetime.combine(
                                posted + timedelta(days=random.randint(5, 30)),
                                datetime.min.time(),
                            ),
                    ))
                    added += 1
                return added

            # ── KB 매물 ──
            kb_li = _add_listings(
                KB_LISTINGS_PER_COMPLEX, "kb", "KB",
                (1.00, 1.15), statuses_active_heavy,
            )
            total_listings += kb_li

            # ── 네이버 부동산 호가 ──
            naver_li = _add_listings(
                NAVER_LISTINGS_PER_COMPLEX, "naver", "NV",
                (0.98, 1.20), statuses_sold_heavy,
            )
            total_listings += naver_li

            # 단지별 커밋 (부분 진행 보존)
            db.commit()

            print(f"  [OK] {cx.name} (id={cx.id}): "
                  f"면적 {len(areas)}개, "
                  f"거래 KB {kb_tx}+국토부 {molit_tx}건, "
                  f"매물 KB {kb_li}+네이버 {naver_li}건")
        print()
        print("=" * 55)
        print("[완료] 12개월 랜덤 데이터 삽입 성공!")
        print(f"  대상 단지: {len(complexes)}개")
        print(f"  KB 시세: {total_prices}건")
        print(f"  실거래가: {total_tx}건")
        print(f"  매물: {total_listings}건")
        print("=" * 55)

    except Exception as e:
        db.rollback()
        print(f"[ERROR] 데이터 삽입 실패: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_12month()
