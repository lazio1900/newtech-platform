"""
시연용 시드 데이터 삽입 스크립트

대상: 서울특별시 영등포구 양평동3가 양평동6차현대아파트 606동 1802호
실제 공개 정보를 기반으로 작성된 시연용 데이터입니다.

사용법:
    cd backend
    python seed_demo_data.py
"""

import sys
from datetime import date, datetime, timedelta

from core.database import SessionLocal, engine
from models import Base
from models.complex import Complex, Area
from models.price_data import KBPrice, Transaction, Listing, ListingStatus


def seed():
    # DB 테이블 생성
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        # 기존 시연 데이터 정리 (중복 방지)
        existing = db.query(Complex).filter(
            Complex.name == "양평동6차현대"
        ).first()
        if existing:
            print(f"[INFO] 기존 시연 데이터 발견 (id={existing.id}), 삭제 후 재삽입합니다.")
            db.query(Listing).filter(Listing.complex_id == existing.id).delete()
            db.query(Transaction).filter(Transaction.complex_id == existing.id).delete()
            db.query(KBPrice).filter(KBPrice.complex_id == existing.id).delete()
            db.query(Area).filter(Area.complex_id == existing.id).delete()
            db.delete(existing)
            db.flush()

        # ──────────────────────────────────────
        # 1. 대상 단지: 양평동6차현대
        # ──────────────────────────────────────
        target = Complex(
            name="양평동6차현대",
            address="서울특별시 영등포구 양평동3가",
            region_code="1156010600",  # 영등포구 양평동3가
            kb_complex_id="3847",
            priority="NORMAL",
            is_active=True,
            collect_listings=True,
            total_households=696,
            corridor_type="계단식",
            build_year=2001,
        )
        db.add(target)
        db.flush()

        # 면적 타입
        area_59 = Area(
            complex_id=target.id,
            exclusive_m2=59.76,
            supply_m2=84.94,
            pyeong=18,
            kb_area_code="059A",
        )
        area_84 = Area(
            complex_id=target.id,
            exclusive_m2=84.97,
            supply_m2=114.81,
            pyeong=25,
            kb_area_code="084A",
        )
        db.add_all([area_59, area_84])
        db.flush()

        print(f"[OK] 단지 등록: {target.name} (id={target.id})")
        print(f"     면적: 59㎡ (id={area_59.id}), 84㎡ (id={area_84.id})")

        # ──────────────────────────────────────
        # 2. KB 시세 데이터 (최근 3개월)
        # ──────────────────────────────────────
        today = date.today()
        now = datetime.utcnow()

        # 59㎡ KB 시세 (단위: 원)
        kb_prices_59 = [
            # (기준일, 일반가, 상위평균가, 하위평균가)
            (today - timedelta(days=84), 1_050_000_000, 1_130_000_000,  980_000_000),
            (today - timedelta(days=77), 1_055_000_000, 1_135_000_000,  985_000_000),
            (today - timedelta(days=70), 1_060_000_000, 1_140_000_000,  990_000_000),
            (today - timedelta(days=63), 1_058_000_000, 1_138_000_000,  988_000_000),
            (today - timedelta(days=56), 1_065_000_000, 1_145_000_000,  995_000_000),
            (today - timedelta(days=49), 1_070_000_000, 1_150_000_000, 1_000_000_000),
            (today - timedelta(days=42), 1_075_000_000, 1_155_000_000, 1_005_000_000),
            (today - timedelta(days=35), 1_080_000_000, 1_160_000_000, 1_010_000_000),
            (today - timedelta(days=28), 1_085_000_000, 1_165_000_000, 1_015_000_000),
            (today - timedelta(days=21), 1_090_000_000, 1_170_000_000, 1_020_000_000),
            (today - timedelta(days=14), 1_095_000_000, 1_175_000_000, 1_025_000_000),
            (today - timedelta(days=7),  1_100_000_000, 1_180_000_000, 1_030_000_000),
            (today,                      1_105_000_000, 1_185_000_000, 1_035_000_000),
        ]

        # 84㎡ KB 시세 (단위: 원)
        kb_prices_84 = [
            (today - timedelta(days=84), 1_300_000_000, 1_400_000_000, 1_210_000_000),
            (today - timedelta(days=77), 1_305_000_000, 1_405_000_000, 1_215_000_000),
            (today - timedelta(days=70), 1_310_000_000, 1_410_000_000, 1_220_000_000),
            (today - timedelta(days=63), 1_308_000_000, 1_408_000_000, 1_218_000_000),
            (today - timedelta(days=56), 1_315_000_000, 1_415_000_000, 1_225_000_000),
            (today - timedelta(days=49), 1_320_000_000, 1_420_000_000, 1_230_000_000),
            (today - timedelta(days=42), 1_330_000_000, 1_430_000_000, 1_240_000_000),
            (today - timedelta(days=35), 1_335_000_000, 1_435_000_000, 1_245_000_000),
            (today - timedelta(days=28), 1_340_000_000, 1_440_000_000, 1_250_000_000),
            (today - timedelta(days=21), 1_345_000_000, 1_445_000_000, 1_255_000_000),
            (today - timedelta(days=14), 1_350_000_000, 1_450_000_000, 1_260_000_000),
            (today - timedelta(days=7),  1_360_000_000, 1_460_000_000, 1_270_000_000),
            (today,                      1_370_000_000, 1_470_000_000, 1_280_000_000),
        ]

        for as_of, gen, high, low in kb_prices_59:
            db.add(KBPrice(
                complex_id=target.id, area_id=area_59.id,
                as_of_date=as_of, general_price=gen,
                high_avg_price=high, low_avg_price=low,
                source="kb", fetched_at=now,
            ))

        for as_of, gen, high, low in kb_prices_84:
            db.add(KBPrice(
                complex_id=target.id, area_id=area_84.id,
                as_of_date=as_of, general_price=gen,
                high_avg_price=high, low_avg_price=low,
                source="kb", fetched_at=now,
            ))

        print(f"[OK] KB 시세: 59㎡ {len(kb_prices_59)}건, 84㎡ {len(kb_prices_84)}건")

        # ──────────────────────────────────────
        # 3. 실거래가 데이터 (최근 3개월)
        # ──────────────────────────────────────
        transactions = [
            # (계약일, 가격(원), 전용면적, 층, 소스)
            (today - timedelta(days=80), 1_040_000_000, 59.76,  7, "kb"),
            (today - timedelta(days=72), 1_260_000_000, 84.97, 12, "kb"),
            (today - timedelta(days=65),   980_000_000, 59.76,  3, "kb"),
            (today - timedelta(days=55), 1_300_000_000, 84.97, 15, "kb"),
            (today - timedelta(days=48), 1_080_000_000, 59.76, 11, "kb"),
            (today - timedelta(days=40), 1_350_000_000, 84.97, 20, "kb"),
            (today - timedelta(days=32), 1_100_000_000, 59.76,  9, "kb"),
            (today - timedelta(days=25), 1_380_000_000, 84.97, 18, "kb"),
            (today - timedelta(days=18), 1_120_000_000, 59.76, 14, "kb"),
            (today - timedelta(days=10), 1_400_000_000, 84.97, 22, "kb"),
            (today - timedelta(days=5),  1_130_000_000, 59.76,  8, "kb"),
        ]

        for contract_dt, price, m2, floor, src in transactions:
            db.add(Transaction(
                complex_id=target.id,
                contract_date=contract_dt, price=price,
                exclusive_m2=m2, floor=floor,
                is_cancelled=False, source=src,
                fetched_at=now,
            ))

        print(f"[OK] 실거래가: {len(transactions)}건")

        # ──────────────────────────────────────
        # 4. 매물/호가 데이터 (현재 활성 매물)
        # ──────────────────────────────────────
        listings = [
            # (매물ID, 호가(원), 전용면적, 층, 상태, 등록일)
            ("KB-YP6H-001", 1_150_000_000, 59.76,  5, ListingStatus.ACTIVE,  today - timedelta(days=12)),
            ("KB-YP6H-002", 1_180_000_000, 59.76, 10, ListingStatus.ACTIVE,  today - timedelta(days=8)),
            ("KB-YP6H-003", 1_200_000_000, 59.76, 15, ListingStatus.ACTIVE,  today - timedelta(days=5)),
            ("KB-YP6H-004", 1_420_000_000, 84.97, 12, ListingStatus.ACTIVE,  today - timedelta(days=15)),
            ("KB-YP6H-005", 1_450_000_000, 84.97, 17, ListingStatus.ACTIVE,  today - timedelta(days=10)),
            ("KB-YP6H-006", 1_480_000_000, 84.97, 21, ListingStatus.ACTIVE,  today - timedelta(days=3)),
            ("KB-YP6H-007", 1_500_000_000, 84.97, 25, ListingStatus.ACTIVE,  today - timedelta(days=1)),
            ("KB-YP6H-008", 1_100_000_000, 59.76,  3, ListingStatus.SOLD,    today - timedelta(days=30)),
            ("KB-YP6H-009", 1_350_000_000, 84.97,  8, ListingStatus.SOLD,    today - timedelta(days=25)),
            ("KB-YP6H-010", 1_130_000_000, 59.76,  7, ListingStatus.REMOVED, today - timedelta(days=20)),
        ]

        for lid, ask, m2, floor, status, posted in listings:
            db.add(Listing(
                complex_id=target.id,
                source_listing_id=lid, ask_price=ask,
                exclusive_m2=m2, floor=floor,
                status=status, posted_at=datetime.combine(posted, datetime.min.time()),
                source="kb", fetched_at=now, last_seen_at=now,
            ))

        print(f"[OK] 매물: {len(listings)}건 (활성 {sum(1 for l in listings if l[4] == ListingStatus.ACTIVE)}건)")

        # ──────────────────────────────────────
        # 5. 인근 유사 단지 (같은 영등포구 양평동)
        # ──────────────────────────────────────
        nearby_complexes = [
            {
                "name": "양평동경남아너스빌",
                "address": "서울특별시 영등포구 양평동3가",
                "kb_complex_id": "NB001",
                "region_code": "1156010600",
                "area_m2": 84.92, "pyeong": 25,
                "total_households": 480, "corridor_type": "계단식", "build_year": 2003,
                "transactions": [
                    (today - timedelta(days=75), 1_150_000_000, 84.92, 10),
                    (today - timedelta(days=40), 1_200_000_000, 84.92, 14),
                    (today - timedelta(days=8),  1_230_000_000, 84.92, 18),
                ],
            },
            {
                "name": "양평동한신더캐슬",
                "address": "서울특별시 영등포구 양평동4가",
                "kb_complex_id": "NB002",
                "region_code": "1156010700",
                "area_m2": 84.98, "pyeong": 25,
                "total_households": 612, "corridor_type": "혼합식", "build_year": 2005,
                "transactions": [
                    (today - timedelta(days=60), 1_280_000_000, 84.98, 8),
                    (today - timedelta(days=30), 1_320_000_000, 84.98, 15),
                    (today - timedelta(days=3),  1_350_000_000, 84.98, 20),
                ],
            },
            {
                "name": "양평동롯데팰리스",
                "address": "서울특별시 영등포구 양평동3가",
                "kb_complex_id": "NB003",
                "region_code": "1156010600",
                "area_m2": 59.88, "pyeong": 18,
                "total_households": 320, "corridor_type": "복도식", "build_year": 1998,
                "transactions": [
                    (today - timedelta(days=70), 950_000_000,  59.88,  5),
                    (today - timedelta(days=35), 980_000_000,  59.88, 10),
                    (today - timedelta(days=12), 1_020_000_000, 59.88, 12),
                ],
            },
            {
                "name": "영등포푸르지오",
                "address": "서울특별시 영등포구 영등포동",
                "kb_complex_id": "NB004",
                "region_code": "1156010100",
                "area_m2": 84.99, "pyeong": 25,
                "total_households": 1024, "corridor_type": "계단식", "build_year": 2010,
                "transactions": [
                    (today - timedelta(days=55), 1_400_000_000, 84.99, 12),
                    (today - timedelta(days=20), 1_450_000_000, 84.99, 22),
                    (today - timedelta(days=2),  1_480_000_000, 84.99, 18),
                ],
            },
            {
                "name": "양평동현대2차",
                "address": "서울특별시 영등포구 양평동3가",
                "kb_complex_id": "NB005",
                "region_code": "1156010600",
                "area_m2": 84.85, "pyeong": 25,
                "total_households": 540, "corridor_type": "계단식", "build_year": 1999,
                "transactions": [
                    (today - timedelta(days=80), 1_050_000_000, 84.85,  6),
                    (today - timedelta(days=45), 1_080_000_000, 84.85, 10),
                    (today - timedelta(days=15), 1_100_000_000, 84.85, 13),
                ],
            },
        ]

        # 인근 단지용 KB 시세도 함께 삽입 (평단가 추이 계산용)
        for nc in nearby_complexes:
            # 기존 중복 정리
            ex = db.query(Complex).filter(Complex.kb_complex_id == nc["kb_complex_id"]).first()
            if ex:
                db.query(Listing).filter(Listing.complex_id == ex.id).delete()
                db.query(Transaction).filter(Transaction.complex_id == ex.id).delete()
                db.query(KBPrice).filter(KBPrice.complex_id == ex.id).delete()
                db.query(Area).filter(Area.complex_id == ex.id).delete()
                db.delete(ex)
                db.flush()

            c = Complex(
                name=nc["name"], address=nc["address"],
                region_code=nc["region_code"],
                kb_complex_id=nc["kb_complex_id"],
                priority="NORMAL", is_active=True, collect_listings=False,
                total_households=nc.get("total_households"),
                corridor_type=nc.get("corridor_type"),
                build_year=nc.get("build_year"),
            )
            db.add(c)
            db.flush()

            a = Area(
                complex_id=c.id,
                exclusive_m2=nc["area_m2"], supply_m2=nc["area_m2"] * 1.35,
                pyeong=nc["pyeong"], kb_area_code=f"0{int(nc['area_m2'])}A",
            )
            db.add(a)
            db.flush()

            # 거래 데이터
            for dt, price, m2, fl in nc["transactions"]:
                db.add(Transaction(
                    complex_id=c.id,
                    contract_date=dt, price=price,
                    exclusive_m2=m2, floor=fl,
                    is_cancelled=False, source="kb", fetched_at=now,
                ))

            # KB 시세 (월별 1건씩, 3개월)
            base_price = nc["transactions"][-1][1]
            for months_ago in range(2, -1, -1):
                as_of = (today.replace(day=15) - timedelta(days=months_ago * 30))
                factor = 1 - (months_ago * 0.02)
                gen_price = int(base_price * factor)
                db.add(KBPrice(
                    complex_id=c.id, area_id=a.id,
                    as_of_date=as_of,
                    general_price=gen_price,
                    high_avg_price=int(gen_price * 1.08),
                    low_avg_price=int(gen_price * 0.92),
                    source="kb", fetched_at=now,
                ))

            print(f"[OK] 인근 단지: {nc['name']} (거래 {len(nc['transactions'])}건)")

        db.commit()
        print("\n" + "=" * 50)
        print("[완료] 시연 데이터 삽입 성공!")
        print(f"  대상 단지: 양평동6차현대 (id={target.id})")
        print(f"  심사 테스트 주소: 서울특별시 영등포구 양평동3가 양평동6차현대아파트 606동 1802호")
        print(f"  인근 유사 단지: {len(nearby_complexes)}개")
        print("=" * 50)

    except Exception as e:
        db.rollback()
        print(f"[ERROR] 시드 데이터 삽입 실패: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
