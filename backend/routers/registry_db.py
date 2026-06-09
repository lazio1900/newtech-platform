"""등기부 DB 조회 보조: /api/registry-db/*

폐쇄망 NICE 6테이블(앱 PG 미러)에 대한 read-only 보조 엔드포인트.
- search: 주소로 부동산고유번호 후보 검색(사내 디렉토리 호출 불가 → 적재된 등기부 한정)
- {unq}/exists: 존재 가드
- {unq}: 결정적 요약 미리보기(폼 조회용, LLM 없음)
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.config import settings
from core.database import get_db
from models import User

router = APIRouter()


def _require_db_mode() -> None:
    """등기부 DB 경로가 구성된 모드(auto/db)에서만 의미. pdf 모드면 503."""
    if settings.registry_source == "pdf":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="등기부 DB 소스가 구성되지 않았습니다. (REGISTRY_SOURCE=auto|db)",
        )


@router.get("/search")
def search_registry(
    sido: Optional[str] = Query(None),
    sigungu: Optional[str] = Query(None),
    dong: Optional[str] = Query(None, description="읍면동명"),
    complex: Optional[str] = Query(None, description="단지명"),
    building: Optional[str] = Query(None, description="동"),
    unit: Optional[str] = Query(None, description="호"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """주소(시도/시군구/읍면동/단지/동/호)로 적재된 등기부의 부동산고유번호 후보를 검색."""
    _require_db_mode()
    from services.registry_db_service import search_registries
    candidates = search_registries(
        db, sido=sido, sigungu=sigungu, dong=dong,
        complex_name=complex, building=building, unit=unit,
    )
    return {"candidates": candidates}


def _normalize_unq(unq_no: str) -> str:
    digits = "".join(ch for ch in unq_no if ch.isdigit())
    if len(digits) != 14:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="부동산고유번호는 숫자 14자리여야 합니다.",
        )
    return digits


@router.get("/{unq_no}/exists")
def check_registry_exists(
    unq_no: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """부동산고유번호로 등기부 DB(6테이블)에 행이 있는지. 신청 폼 입력 가드용."""
    _require_db_mode()
    digits = _normalize_unq(unq_no)
    from services.registry_db_service import registry_exists
    return {"rles_unq_no": digits, "exists": registry_exists(db, digits)}


@router.get("/{unq_no}")
def get_registry_preview(
    unq_no: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """부동산고유번호의 등기부 결정적 요약(주소·근저당 합계·소유자·신선도). 폼 조회용(LLM 없음)."""
    _require_db_mode()
    digits = _normalize_unq(unq_no)
    from services.registry_db_service import build_preview
    return build_preview(db, digits)
