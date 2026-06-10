"""내부망(CCTR_*) 유사 단지 비교 — 좌표 없는 폐쇄망용.

외부 모드의 lat/lng 1km 반경 대신 **법정동(→시군구) 행정구역 + 평형/연식/규모/시세 유사도**로
같은 생활권의 비교 단지를 고른다. 시세는 CCTR KB 시세(일반거래가, 원) 기준.

반환은 외부와 동일한 NearbyPropertyTrends(좌표·거리·반경은 None) — 리스트/LLM 재사용.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from models.complex import Area, Complex
from models.internal_kb import CctrKbAptM, CctrKbAptQtnL
from models.response_models import NearbyPropertyTrends, SimilarProperty
from services.complex_score_service import _year_int
from services.internal_market_service import _won, _ymd

logger = logging.getLogger(__name__)

_M2_TOL = 10.0  # 평형 매칭 허용 ㎡


def _kb_prices(db: Session, kb: str, pntp: Optional[str], cutoff: date):
    """단지의 KB 일반거래가 시계열(원). 평형 일치 우선, 없으면 단지 전체.
    반환: (최근가, cutoff 이후 첫 시점가) — 둘째는 3개월 변동률 기준."""
    rows = [
        r for r in db.query(CctrKbAptQtnL).filter(CctrKbAptQtnL.kb_qtn_rles_gd_cd == kb).all()
        if r.deal_gnrl_txcs is not None and _ymd(r.ivst_base_dt)
    ]
    if pntp:
        matched = [r for r in rows if r.pntp_seqno == pntp]
        rows = matched or rows
    if not rows:
        return None, None
    rows.sort(key=lambda r: r.ivst_base_dt)
    recent = _won(rows[-1].deal_gnrl_txcs)
    base = next((r for r in rows if _ymd(r.ivst_base_dt) >= cutoff), rows[0])
    return recent, _won(base.deal_gnrl_txcs)


def _age(built_year) -> Optional[int]:
    yr = _year_int(built_year)
    return date.today().year - yr if yr else None


def _match_area(areas: List[Area], target_m2: Optional[float]) -> Optional[Area]:
    valid = [a for a in areas if a.exclusive_m2]
    if not valid:
        return None
    if target_m2 is None:
        return valid[0]
    best = min(valid, key=lambda a: abs(a.exclusive_m2 - target_m2))
    return best if abs(best.exclusive_m2 - target_m2) <= _M2_TOL else None


def build_internal_nearby(
    db: Session,
    target_complex: Complex,
    target_area: Optional[Area],
    max_count: int = 5,
) -> Optional[NearbyPropertyTrends]:
    if not target_complex.kb_complex_id:
        return None

    today = date.today()
    cutoff_3m = today - timedelta(days=90)
    target_m2 = target_area.exclusive_m2 if target_area else None
    target_pntp = target_area.kb_area_code if target_area else None
    target_age = _age(target_complex.built_year)
    target_units = target_complex.total_households or 0
    target_recent_price, _ = _kb_prices(db, target_complex.kb_complex_id, target_pntp, cutoff_3m)

    # 후보 — CCTR 적재(시세 존재) + 같은 법정동, 부족하면 시군구로 확장.
    def _in_scope(scope_filter):
        return (
            db.query(Complex)
            .join(CctrKbAptM, CctrKbAptM.kb_qtn_rles_gd_cd == Complex.kb_complex_id)
            .filter(Complex.id != target_complex.id, scope_filter)
            .all()
        )

    scope = None
    cands: List[Complex] = []
    if target_complex.dong_code:
        cands = _in_scope(Complex.dong_code == target_complex.dong_code)
        scope = f"법정동 {target_complex.dong_name or target_complex.dong_code}"
    if len(cands) < max_count and target_complex.region_code:
        sigungu = target_complex.region_code[:5]
        seen = {c.id for c in cands}
        cands += [c for c in _in_scope(Complex.region_code.like(f"{sigungu}%")) if c.id not in seen]
        if len(cands) > len(seen):
            scope = f"시군구 {target_complex.dong_name.split()[0] if target_complex.dong_name else sigungu}" if not seen else scope
    if not cands:
        return None

    # 후보별 매칭 평형 + KB 시세 + 유사도
    scored = []
    for c in cands:
        area = _match_area(c.areas, target_m2)
        if area is None:
            continue
        recent, base = _kb_prices(db, c.kb_complex_id, area.kb_area_code, cutoff_3m)
        if not recent:
            continue
        c_age = _age(c.built_year)

        # 유사도(거리 제외): 평형 35 / 가격 30 / 연식 20 / 세대수 15
        s_a = 1.0
        if target_m2 and area.exclusive_m2:
            s_a = max(0.0, 1.0 - abs(area.exclusive_m2 - target_m2) / 15.0)
        if target_recent_price and target_recent_price > 0:
            s_p = max(0.0, 1.0 - abs(recent - target_recent_price) / target_recent_price / 0.50)
        else:
            s_p = 0.5
        s_y = 1.0
        if target_age is not None and c_age is not None:
            s_y = max(0.0, 1.0 - abs(c_age - target_age) / 20.0)
        s_u = 1.0
        if target_units > 0 and c.total_households:
            s_u = min(target_units, c.total_households) / max(target_units, c.total_households)
        sim = round(s_a * 0.35 + s_p * 0.30 + s_y * 0.20 + s_u * 0.15, 3)

        change = 0.0
        if base and base > 0 and base != recent:
            change = round((recent - base) / base, 3)
        diff_pct = (
            round((recent - target_recent_price) / target_recent_price * 100, 1)
            if target_recent_price and target_recent_price > 0 else None
        )
        parts = (c.address or "").split()
        scored.append((sim, change, SimilarProperty(
            name=c.name,
            sido=parts[0] if parts else "",
            sigungu=parts[1] if len(parts) > 1 else "",
            address=c.address or "",
            units=c.total_households or 0,
            age=c_age or 0,
            area=int(area.pyeong) if area.pyeong else (int((area.exclusive_m2 or 0) / 3.305785) if area.exclusive_m2 else 0),
            exclusive_m2=area.exclusive_m2,
            lat=None, lng=None, distance_m=None,
            similarity=sim,
            recent_price=recent,
            price_change_rate=change,
            price_diff_pct=diff_pct,
        )))

    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    scored = scored[:max_count]
    avg_change = round(sum(ch for _, ch, _ in scored) / len(scored), 3)

    return NearbyPropertyTrends(
        target_lat=None, target_lng=None,
        target_recent_price=target_recent_price,
        radius_m=None, scope=scope,
        avg_change_rate=avg_change,
        similar_properties=[sp for _, _, sp in scored],
    )
