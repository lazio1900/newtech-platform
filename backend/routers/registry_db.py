"""등기부 DB 조회 보조: /api/registry-db/*

폐쇄망 NICE 6테이블(앱 PG 미러)에 대한 read-only 보조 엔드포인트.
현재는 신청 폼의 부동산고유번호 입력 가드(존재 확인)만 제공.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.config import settings
from core.database import get_db
from models import User

router = APIRouter()


@router.get("/{unq_no}/exists")
def check_registry_exists(
    unq_no: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """부동산고유번호로 등기부 DB(6테이블)에 행이 있는지. 신청 폼 입력 가드용.

    DB 소스 미구성(registry_source="pdf")이면 503 — 가드는 DB경로에서만 의미.
    """
    if settings.registry_source == "pdf":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="등기부 DB 소스가 구성되지 않았습니다.",
        )
    digits = "".join(ch for ch in unq_no if ch.isdigit())
    if len(digits) != 14:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="부동산고유번호는 숫자 14자리여야 합니다.",
        )
    from services.registry_db_service import registry_exists
    return {"rles_unq_no": digits, "exists": registry_exists(db, digits)}
