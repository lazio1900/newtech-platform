"""행정구역 라우터 — 시도/시군구 목록.

complexes 테이블에서 단지 등록된 region_code 만 노출 (빈 지역 표시 안 함).
"""
from typing import List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.database import get_db
from core.region_codes import (
    eupmyeondong_name,
    list_eupmyeondong,
    sido_name,
    sigungu_name,
)
from models import Complex, User

router = APIRouter()


class SidoItem(BaseModel):
    code: str
    name: str
    count: int


class SigunguItem(BaseModel):
    code: str
    name: str
    count: int


class EupmyeondongItem(BaseModel):
    code: str
    name: str


@router.get("/sido", response_model=List[SidoItem])
def list_sido(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """단지가 등록된 시도 목록 (단지 수 포함, 단지 많은 순)."""
    rows = (
        db.query(
            func.substr(Complex.region_code, 1, 2).label("code"),
            func.count(Complex.id).label("cnt"),
        )
        .filter(Complex.region_code.isnot(None))
        .group_by(func.substr(Complex.region_code, 1, 2))
        .all()
    )
    items = [
        SidoItem(code=r.code, name=sido_name(r.code), count=r.cnt)
        for r in rows
        if r.code
    ]
    items.sort(key=lambda x: x.name)
    return items


@router.get("/sigungu", response_model=List[SigunguItem])
def list_sigungu(
    sido: str = Query(..., description="시도 코드 2자리 (예: 11)", min_length=2, max_length=2),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """선택한 시도의 시군구 목록 (단지 수 포함)."""
    rows = (
        db.query(
            Complex.region_code,
            func.count(Complex.id).label("cnt"),
        )
        .filter(Complex.region_code.like(f"{sido}%"))
        .filter(func.length(Complex.region_code) >= 5)
        .group_by(Complex.region_code)
        .all()
    )
    items = [
        SigunguItem(code=r.region_code, name=sigungu_name(r.region_code), count=r.cnt)
        for r in rows
        if r.region_code
    ]
    items.sort(key=lambda x: x.name)
    return items


@router.get("/eupmyeondong", response_model=List[EupmyeondongItem])
def list_eupmyeondong_endpoint(
    sigungu: str = Query(..., description="시군구 코드 5자리 (예: 11680)", min_length=5, max_length=5),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """선택한 시군구의 읍면동 목록.

    DB의 단지 dong_code DISTINCT 우선 (newtech_data가 채운 실제 데이터).
    DB에 dong_code가 없으면 정적 매핑(EUPMYEONDONG_NAMES) 폴백.
    """
    # 1) DB에서 단지가 등록된 동 코드 + 이름 조회
    rows = (
        db.query(Complex.dong_code, Complex.dong_name)
        .filter(Complex.region_code == sigungu)
        .filter(Complex.dong_code.isnot(None))
        .distinct()
        .all()
    )
    db_items: dict[str, str] = {}
    for code, name in rows:
        if code:
            db_items[code] = name or eupmyeondong_name(code) or code

    if db_items:
        items = [EupmyeondongItem(code=c, name=n) for c, n in db_items.items()]
    else:
        # 폴백: 정적 매핑
        items = [EupmyeondongItem(**e) for e in list_eupmyeondong(sigungu)]

    items.sort(key=lambda x: x.name)
    return items
