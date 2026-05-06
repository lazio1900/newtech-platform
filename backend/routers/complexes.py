"""단지(Complex) 조회 라우터.

수집기(별도 프로젝트)가 등록·갱신한 데이터를 read-only로 노출 (ADR-002, ADR-003).
"""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, literal, or_
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.database import get_db
from models import Area, Complex, PriorityLevel, User


# daum buildingName 등에 자주 붙지만 KB DB에는 빠진 흔한 접미사
_APT_SUFFIXES = (
    "아파트", "주상복합", "오피스텔", "맨션", "빌라", "타운", "단지", "주공",
)


def _strip_apt_suffix(s: str) -> str:
    """단지명 끝의 흔한 접미사 제거 (e.g., '은마아파트' → '은마')."""
    s = s.strip()
    for suf in _APT_SUFFIXES:
        if s.endswith(suf) and len(s) > len(suf):
            return s[: -len(suf)].strip()
    return s

router = APIRouter()


class AreaSchema(BaseModel):
    id: Optional[int] = None
    exclusive_m2: float
    supply_m2: Optional[float] = None
    pyeong: Optional[float] = None
    kb_area_code: Optional[str] = None

    class Config:
        from_attributes = True


class ComplexSchema(BaseModel):
    id: int
    name: str
    address: str
    region_code: Optional[str]
    dong_code: Optional[str] = None
    dong_name: Optional[str] = None
    kb_complex_id: Optional[str]
    priority: Optional[PriorityLevel] = None
    is_active: Optional[bool] = None
    collect_listings: Optional[bool] = None
    total_households: Optional[int] = None
    hallway_type: Optional[str] = None
    built_year: Optional[str] = None
    road_address: Optional[str] = None
    total_buildings: Optional[int] = None
    max_floor: Optional[int] = None
    total_parking: Optional[int] = None
    heating_type: Optional[str] = None
    builder: Optional[str] = None
    areas: List[AreaSchema] = []

    class Config:
        from_attributes = True


class PaginatedComplexResponse(BaseModel):
    items: List[ComplexSchema]
    total: int


@router.get("", response_model=PaginatedComplexResponse)
def list_complexes(
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    region_code: Optional[str] = None,
    dong_code: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """단지 목록 (서버 사이드 페이지네이션).

    region_code: 시군구 5자리 prefix 매칭
    dong_code: 법정동 10자리 정확 매칭 (있을 경우 동 단위로 좁힘)
    """
    query = db.query(Complex)

    if is_active is not None:
        query = query.filter(Complex.is_active == is_active)

    if region_code:
        query = query.filter(Complex.region_code.like(f"{region_code}%"))

    if dong_code:
        query = query.filter(Complex.dong_code == dong_code)

    if search:
        s = search.strip()
        s_short = _strip_apt_suffix(s)
        q = f"%{s}%"
        q_short = f"%{s_short}%"

        # 양방향 매칭 — daum buildingName "은마아파트" 가 DB 단지명 "은마" 와도 매칭되도록
        match_filter = or_(
            Complex.name.ilike(q),                                      # name ⊃ search
            Complex.name.ilike(q_short),                                # name ⊃ search(접미사 제거)
            literal(s).ilike(func.concat("%", Complex.name, "%")),      # search ⊃ name (역방향)
            Complex.address.ilike(q),
            Complex.kb_complex_id.ilike(q),
            Complex.region_code.ilike(q),
        )
        query = query.filter(match_filter)

        total = query.count()
        # 검색 시: 매칭 정확도 우선 정렬 — 단지명이 검색어로 시작하면 1순위, 그 외 길이 짧은 순
        starts_with_search = func.lower(Complex.name).like(f"{s.lower()}%")
        starts_with_short = func.lower(Complex.name).like(f"{s_short.lower()}%")
        items = (
            query.order_by(
                starts_with_search.desc(),
                starts_with_short.desc(),
                func.length(Complex.name).asc(),
                Complex.name,
            )
            .offset(skip)
            .limit(limit)
            .all()
        )
        return PaginatedComplexResponse(items=items, total=total)

    total = query.count()
    items = query.order_by(Complex.name).offset(skip).limit(limit).all()
    return PaginatedComplexResponse(items=items, total=total)


@router.get("/region-counts")
def get_region_counts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """시/도별, 시/군/구별 단지 수."""
    rows = db.query(Complex.region_code).filter(Complex.region_code.isnot(None)).all()

    sido: Dict[str, int] = {}
    region: Dict[str, int] = {}
    for (code,) in rows:
        if code and len(code) >= 2:
            sido[code[:2]] = sido.get(code[:2], 0) + 1
        if code and len(code) >= 5:
            region[code[:5]] = region.get(code[:5], 0) + 1
    return {"sido_counts": sido, "region_counts": region}


@router.get("/{complex_id}", response_model=ComplexSchema)
def get_complex(
    complex_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """단지 상세 조회."""
    complex_obj = db.query(Complex).filter(Complex.id == complex_id).first()
    if not complex_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complex not found")
    return complex_obj


@router.get("/{complex_id}/areas", response_model=List[AreaSchema])
def list_complex_areas(
    complex_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """단지의 평형 목록 (신청 폼 평형 드롭다운용)."""
    complex_obj = db.query(Complex).filter(Complex.id == complex_id).first()
    if not complex_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complex not found")
    areas = (
        db.query(Area)
        .filter(Area.complex_id == complex_id)
        .order_by(Area.exclusive_m2.asc())
        .all()
    )
    return areas
