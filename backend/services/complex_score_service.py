"""단지·물건 특성 점수 — 내부형식(CCTR_*) 데이터 기반 (폐쇄망용).

폐쇄망(internal_only)은 입지 좌표·주변시설이 없어 facility 기반 입지점수를 못 낸다.
대신 단지 자체 특성(규모/연식/주차/시세안정성/위상)을 0~100 으로 환산해 담보 적합성을 본다.
입력은 원시값(ORM 무관) — 호출측(analysis_service)에서 CCTR/시세에서 모아 전달.

임계값은 도메인 기본값(질권 담보 적합성 관점)이며, 운영 튜닝 여지가 있다.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from models.response_models import ComplexScores


def _year_int(built_year) -> Optional[int]:
    """준공연도 파싱 — 정상 형식(YYYY / YYYYMM)만. 오염값(YYYYMMDD·잘못된 월·미래연도)은 None."""
    digits = "".join(c for c in str(built_year or "") if c.isdigit())
    if len(digits) == 4:
        year, month = int(digits), 1
    elif len(digits) == 6:
        year, month = int(digits[:4]), int(digits[4:6])
    else:
        return None
    if 1900 <= year <= date.today().year and 1 <= month <= 12:
        return year
    return None


def _units_pt(total_households: Optional[int]) -> int:
    u = total_households or 0
    if u >= 2000:
        return 100
    if u >= 1000:
        return 90
    if u >= 500:
        return 75
    if u >= 300:
        return 60
    if u >= 100:
        return 45
    if u > 0:
        return 30
    return 50  # 미상 — 중립


def _dong_pt(total_buildings: Optional[int]) -> Optional[int]:
    d = total_buildings or 0
    if d >= 15:
        return 100
    if d >= 10:
        return 85
    if d >= 7:
        return 70
    if d >= 5:
        return 55
    if d >= 3:
        return 40
    if d > 0:
        return 28
    return None  # 미상


def _scale_score(total_households: Optional[int], total_buildings: Optional[int]) -> int:
    """단지 규모 — 세대수 80% + 동수 20%. 대단지일수록 환금성·관리 우수."""
    u = _units_pt(total_households)
    d = _dong_pt(total_buildings)
    if d is None:
        return u
    return round(u * 0.8 + d * 0.2)


def _age_score(built_year) -> int:
    """연식 — 준공 경과년수. 신축일수록 담보가치 안정."""
    yr = _year_int(built_year)
    if yr is None:
        return 50
    age = date.today().year - yr
    if age <= 3:
        return 100
    if age <= 7:
        return 92
    if age <= 10:
        return 85
    if age <= 15:
        return 75
    if age <= 20:
        return 65
    if age <= 30:
        return 50
    if age <= 40:
        return 35
    return 25


def _parking_score(total_parking: Optional[int], total_households: Optional[int]) -> int:
    """주차 편의 — 세대당 주차대수."""
    if not total_parking or not total_households or total_households <= 0:
        return 50
    ratio = total_parking / total_households
    if ratio >= 1.5:
        return 100
    if ratio >= 1.2:
        return 92
    if ratio >= 1.0:
        return 82
    if ratio >= 0.8:
        return 70
    if ratio >= 0.6:
        return 55
    if ratio >= 0.4:
        return 40
    return 28


def _price_stability_score(low: Optional[int], est: Optional[int], high: Optional[int]) -> int:
    """시세 안정성 — 매매 하한~상한 스프레드(/일반거래가). 좁을수록 가격대 명확 = 담보평가 신뢰↑."""
    if not est or est <= 0 or low is None or high is None or high < low or low < 0:
        return 50
    spread = (high - low) / est
    if spread <= 0.05:
        return 100
    if spread <= 0.08:
        return 90
    if spread <= 0.12:
        return 78
    if spread <= 0.18:
        return 62
    if spread <= 0.25:
        return 48
    return 35


def _landmark_score(max_floor: Optional[int], total_buildings: Optional[int]) -> int:
    """단지 위상 — 최고층 70% + 동수 30%. 고층·대단지 랜드마크성."""
    f = max_floor or 0
    if f >= 40:
        fp: Optional[int] = 100
    elif f >= 30:
        fp = 88
    elif f >= 25:
        fp = 78
    elif f >= 20:
        fp = 68
    elif f >= 15:
        fp = 55
    elif f >= 10:
        fp = 42
    elif f > 0:
        fp = 30
    else:
        fp = None
    dp = _dong_pt(total_buildings)
    if fp is None and dp is None:
        return 50
    if fp is None:
        return dp if dp is not None else 50
    if dp is None:
        return fp
    return round(fp * 0.7 + dp * 0.3)


def _interpret_mixed_use(apst_yncd) -> Optional[bool]:
    """APST_YNCD(주상복합여부코드) → bool. 'YNCD'(여부코드)이므로 Y/N·1/0 계열로 판정.
    명확한 값만 판정하고 미지의 코드는 None(미상) — 거꾸로 표시되느니 미표시(오판 방지).
    실 정보계 코드가 '01'/'02' 계열이면 아래 집합에 추가."""
    if apst_yncd is None:
        return None
    s = str(apst_yncd).strip().upper()
    if s in ("Y", "1", "T", "주상복합") or "주상" in s:
        return True
    if s in ("N", "0", "00", "F"):
        return False
    return None


def compute_complex_scores(
    *,
    total_households: Optional[int] = None,
    total_buildings: Optional[int] = None,
    max_floor: Optional[int] = None,
    built_year=None,
    total_parking: Optional[int] = None,
    apst_yncd=None,
    kb_low: Optional[int] = None,
    kb_estimated: Optional[int] = None,
    kb_high: Optional[int] = None,
) -> ComplexScores:
    return ComplexScores(
        scale=_scale_score(total_households, total_buildings),
        age=_age_score(built_year),
        parking=_parking_score(total_parking, total_households),
        price_stability=_price_stability_score(kb_low, kb_estimated, kb_high),
        landmark=_landmark_score(max_floor, total_buildings),
        is_mixed_use=_interpret_mixed_use(apst_yncd),
    )
