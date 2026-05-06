"""데모 도메인 데이터 시드 (개발용).

기존 인메모리 더미 데이터를 DB에 적재.
사전 조건: scripts/seed_users.py 실행 (admin/audit/customer 사용자 존재).

사용법:
    cd backend
    python scripts/seed_demo.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings
from core.database import SessionLocal
from models import (
    ApplicationStatus,
    LoanApplication,
    MonitoringLoan,
    SearchField,
    SearchHistory,
)
from services import application_service, history_service, monitoring_service, user_service


SAMPLE_APPLICATIONS = [
    ("서울시 강남구 대치동 은마아파트 3동 502호", 850_000_000, 24),
    ("서울시 서초구 반포동 아크로리버파크 1동 1801호", 1_200_000_000, 36),
    ("서울시 송파구 잠실동 잠실엘스 208동 1503호", 920_000_000, 12),
]

SAMPLE_MONITORING = [
    {
        "company_name": "파란캐피탈대부", "ceo_name": "김대출",
        "property_address": "서울시 강남구 대치동 은마아파트 3동 502호",
        "loan_amount": 680_000_000, "execution_price": 1_050_000_000,
        "current_price": 1_120_000_000, "execution_date": date(2024, 6, 15),
    },
    {
        "company_name": "하늘캐피탈대부", "ceo_name": "이하늘",
        "property_address": "서울시 서초구 반포동 아크로리버파크 1동 1801호",
        "loan_amount": 1_100_000_000, "execution_price": 1_800_000_000,
        "current_price": 1_750_000_000, "execution_date": date(2024, 7, 22),
    },
    {
        "company_name": "파란캐피탈대부", "ceo_name": "김대출",
        "property_address": "서울시 송파구 잠실동 잠실엘스 208동 1503호",
        "loan_amount": 750_000_000, "execution_price": 1_200_000_000,
        "current_price": 1_180_000_000, "execution_date": date(2024, 8, 10),
    },
    {
        "company_name": "바다저축은행대부", "ceo_name": "박바다",
        "property_address": "서울시 강남구 역삼동 타워팰리스 2차 3동 4501호",
        "loan_amount": 900_000_000, "execution_price": 1_350_000_000,
        "current_price": 1_400_000_000, "execution_date": date(2024, 9, 5),
    },
    {
        "company_name": "노을캐피탈대부", "ceo_name": "정노을",
        "property_address": "서울시 용산구 한남동 한남더힐 109동 301호",
        "loan_amount": 1_500_000_000, "execution_price": 2_200_000_000,
        "current_price": 2_350_000_000, "execution_date": date(2024, 10, 18),
    },
    {
        "company_name": "해돋이금융대부", "ceo_name": "최해돋",
        "property_address": "서울시 마포구 아현동 마포래미안푸르지오 105동 2201호",
        "loan_amount": 520_000_000, "execution_price": 780_000_000,
        "current_price": 720_000_000, "execution_date": date(2024, 11, 2),
    },
    {
        "company_name": "별빛캐피탈", "ceo_name": "한별빛",
        "property_address": "서울시 성동구 금호동 옥수리버뷰 201동 1502호",
        "loan_amount": 600_000_000, "execution_price": 950_000_000,
        "current_price": 940_000_000, "execution_date": date(2025, 1, 8),
    },
    {
        "company_name": "파란캐피탈대부", "ceo_name": "김대출",
        "property_address": "서울시 양천구 목동 목동신시가지 7단지 702동 801호",
        "loan_amount": 480_000_000, "execution_price": 820_000_000,
        "current_price": 810_000_000, "execution_date": date(2025, 1, 25),
    },
]

SAMPLE_COMPANIES = [
    "파란캐피탈대부", "파란금융대부", "파란저축은행대부",
    "하늘캐피탈대부", "하늘금융저축은행",
    "바다캐피탈", "바다저축은행대부",
    "산캐피탈대부", "산금융대부",
    "들판캐피탈", "들판저축은행",
    "노을캐피탈대부", "해돋이금융대부",
    "별빛캐피탈", "무지개저축은행대부",
    "JB캐피탈대부", "KB금융대부", "신한캐피탈대부",
]

SAMPLE_ADDRESSES = [
    "서울시 강남구 대치동 은마아파트",
    "서울시 강남구 대치동 은마아파트 2동 1203호",
    "서울시 강남구 역삼동 타워팰리스",
    "서울시 서초구 반포동 아크로리버파크",
    "서울시 서초구 잠원동 신반포자이",
    "서울시 송파구 잠실동 잠실엘스",
    "서울시 송파구 잠실동 리센츠",
    "서울시 강남구 청담동 청담자이",
    "서울시 강남구 논현동 힐스테이트",
    "서울시 서초구 서초동 래미안",
    "서울시 양천구 목동 목동신시가지",
    "서울시 마포구 아현동 마포래미안",
    "서울시 용산구 한남동 한남더힐",
    "서울시 성동구 금호동 옥수리버뷰",
    "서울시 강서구 등촌동 등촌주공아파트",
    "서울시 노원구 상계동 상계주공아파트",
    "서울시 은평구 응암동 은평뉴타운",
]


def seed_applications(db, customer_user) -> int:
    if db.query(LoanApplication).count() > 0:
        print("[seed_demo] applications: skip (data exists)")
        return 0
    created = 0
    for address, amount, duration in SAMPLE_APPLICATIONS:
        application_service.submit(
            db,
            applicant=customer_user,
            company_name=customer_user.company_name or "파란캐피탈대부",
            ceo_name=customer_user.ceo_name or "김대출",
            property_address=address,
            loan_amount=amount,
            loan_duration=duration,
        )
        created += 1
    print(f"[seed_demo] applications: created {created}")
    return created


def seed_monitoring(db, auditor_user) -> int:
    if db.query(MonitoringLoan).count() > 0:
        print("[seed_demo] monitoring: skip (data exists)")
        return 0
    created = 0
    for sample in SAMPLE_MONITORING:
        loan = monitoring_service.add_loan(
            db,
            auditor=auditor_user,
            company_name=sample["company_name"],
            ceo_name=sample["ceo_name"],
            property_address=sample["property_address"],
            loan_amount=sample["loan_amount"],
            execution_price=sample["execution_price"],
            execution_date=sample["execution_date"],
        )
        # 데모용으로 current_price 직접 설정 (집행시점과 다른 시세 시뮬)
        loan.current_price = sample["current_price"]
        db.commit()
        created += 1
    print(f"[seed_demo] monitoring: created {created}")
    return created


def seed_history(db) -> int:
    if db.query(SearchHistory).count() > 0:
        print("[seed_demo] history: skip (data exists)")
        return 0
    for c in SAMPLE_COMPANIES:
        history_service.record(db, field=SearchField.COMPANY, value=c)
    for a in SAMPLE_ADDRESSES:
        history_service.record(db, field=SearchField.ADDRESS, value=a)
    total = len(SAMPLE_COMPANIES) + len(SAMPLE_ADDRESSES)
    print(f"[seed_demo] history: created {total}")
    return total


def main() -> int:
    if settings.is_production:
        print("[seed_demo] ERROR: production 환경에서는 실행하지 않습니다.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        customer = user_service.get_by_user_id(db, "customer")
        auditor = user_service.get_by_user_id(db, "audit")
        if not customer or not auditor:
            print("[seed_demo] ERROR: customer/audit 사용자가 없습니다. 먼저 seed_users.py 실행.", file=sys.stderr)
            return 1

        seed_applications(db, customer)
        seed_monitoring(db, auditor)
        seed_history(db)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
