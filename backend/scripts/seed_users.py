"""기본 사용자 시드 (개발용).

운영 환경에서는 사용 금지. 비밀번호가 약함.

사용법:
    cd backend
    python scripts/seed_users.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# scripts/ 가 아닌 backend/ 를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings
from core.database import SessionLocal
from models import UserRole
from services import user_service


# (user_id, password, role, company_name, ceo_name, business_number, phone)
DEFAULT_USERS = [
    ("admin",    os.getenv("SEED_ADMIN_PASSWORD",    "admin1234"),    UserRole.ADMIN,    "JB우리캐피탈", "관리자",   None, None),
    ("audit",    os.getenv("SEED_AUDITOR_PASSWORD",  "audit1234"),    UserRole.AUDITOR,  "JB우리캐피탈", "박심사",   None, None),
    ("customer", os.getenv("SEED_CUSTOMER_PASSWORD", "customer1234"), UserRole.CUSTOMER, "파란캐피탈대부", "김대출", "123-45-67890", "02-1234-5678"),
]


def main() -> int:
    if settings.is_production:
        print("[seed_users] ERROR: production 환경에서는 실행하지 않습니다.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        for user_id, password, role, company, ceo, biz, phone in DEFAULT_USERS:
            existing = user_service.get_by_user_id(db, user_id)
            if existing:
                print(f"[seed_users] skip (exists): {user_id} ({existing.role.value})")
                continue
            user_service.create_user(
                db,
                user_id=user_id,
                password=password,
                role=role,
                company_name=company,
                ceo_name=ceo,
                business_number=biz,
                phone=phone,
            )
            print(f"[seed_users] created: {user_id} ({role.value})")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
