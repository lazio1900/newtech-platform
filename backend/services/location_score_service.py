"""입지점수 산출 서비스.

ComplexFacility (school/subway/hospital/park) + Complex.total_households 를
LocationScores 6개 카테고리로 환산.

데이터 부족 시 None 반환 — 호출 측에서 더미 폴백.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from models.complex import Complex
from models.facility import ComplexFacility
from models.response_models import LocationScores

logger = logging.getLogger(__name__)


def _distance_score(d_m: Optional[int]) -> int:
    """거리(m) → 0~100 점수. 가까울수록 고점."""
    if d_m is None:
        return 0
    if d_m <= 300:
        return 100
    if d_m <= 500:
        return 90
    if d_m <= 800:
        return 75
    if d_m <= 1200:
        return 55
    if d_m <= 1800:
        return 35
    return 15


def _nearest(facilities: List[ComplexFacility]) -> Optional[ComplexFacility]:
    """distance_m 이 채워진 것 중 최단."""
    valid = [f for f in facilities if f.distance_m is not None]
    return min(valid, key=lambda f: f.distance_m) if valid else None


def _within(facilities: List[ComplexFacility], radius_m: int) -> List[ComplexFacility]:
    return [f for f in facilities if f.distance_m is not None and f.distance_m <= radius_m]


def _station_walk_score(subways: List[ComplexFacility]) -> int:
    """역세권 도보 — 가장 가까운 지하철 거리."""
    near = _nearest(subways)
    return _distance_score(near.distance_m) if near else 0


def _commute_score(subways: List[ComplexFacility]) -> int:
    """통근 편의 — 거리 60% + 노선 다양성 40%."""
    near = _nearest(subways)
    if not near:
        return 0
    distance_pt = _distance_score(near.distance_m)
    # 호선 다양성 — sub_type(예: "서울-4호선") 고유 수
    line_set = {f.sub_type for f in subways if f.sub_type}
    line_pt = min(len(line_set) * 30, 100)
    return int(distance_pt * 0.6 + line_pt * 0.4)


def _school_walk_score(schools: List[ComplexFacility]) -> int:
    """학군 도보 — 가장 가까운 초등학교 거리."""
    elementary = [s for s in schools if s.sub_type == "elementary"]
    near = _nearest(elementary)
    return _distance_score(near.distance_m) if near else 0


def _units_score(total_households: Optional[int]) -> int:
    """세대수 점수."""
    if total_households is None or total_households <= 0:
        return 50
    if total_households >= 2000:
        return 100
    if total_households >= 1000:
        return 90
    if total_households >= 500:
        return 75
    if total_households >= 300:
        return 60
    if total_households >= 100:
        return 45
    return 30


def _living_env_score(hospitals: List[ComplexFacility]) -> int:
    """생활환경 — 1km 내 병원 개수."""
    count = len(_within(hospitals, 1000))
    if count >= 30:
        return 100
    if count >= 20:
        return 85
    if count >= 10:
        return 70
    if count >= 5:
        return 55
    if count >= 1:
        return 40
    return 25


def _nature_env_score(parks: List[ComplexFacility]) -> int:
    """자연환경 — 최단 공원 거리 70% + 1km 내 공원 수 30%."""
    if not parks:
        return 20
    near = _nearest(parks)
    distance_pt = _distance_score(near.distance_m) if near else 0
    count = len(_within(parks, 1000))
    count_pt = min(count * 8, 80)
    return int(distance_pt * 0.7 + count_pt * 0.3)


def compute_location_scores(
    db: Session,
    complex_obj: Complex,
) -> Optional[LocationScores]:
    """단지의 facility 데이터 기반 입지점수 산출.

    facility 가 한 건도 없으면 None 반환 (더미 폴백 유도).
    부분 보유 시(예: school 만) 빠진 카테고리는 0~50 의 낮은 점수로 채움.
    """
    facilities = (
        db.query(ComplexFacility)
        .filter(ComplexFacility.complex_id == complex_obj.id)
        .all()
    )
    if not facilities:
        return None

    schools = [f for f in facilities if f.facility_type == "school"]
    subways = [f for f in facilities if f.facility_type == "subway"]
    hospitals = [f for f in facilities if f.facility_type == "hospital"]
    parks = [f for f in facilities if f.facility_type == "park"]

    return LocationScores(
        station_walk=_station_walk_score(subways),
        commute_time=_commute_score(subways),
        school_walk=_school_walk_score(schools),
        units_score=_units_score(complex_obj.total_households),
        living_env=_living_env_score(hospitals),
        nature_env=_nature_env_score(parks),
    )
