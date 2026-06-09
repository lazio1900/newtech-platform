"""INTERNAL_ONLY 모드의 KB 시장데이터 — 크롤 app-schema 대신 내부형식 CCTR_* 에서 산출.

get_real_market_data(크롤) 와 동일한 dict 계약을 반환하되 출처가 CCTR_* 6테이블(models/internal_kb).
CCTR_* 에 없는 정보(위경도·매물(naver)·인근동향)는 None → 호출측에서 "확인 불가".

식별 브리지: 신청/분석은 app-schema id(complex_id/area_id)로 동작하므로 complexes 행에서
kb_complex_id 만 읽어 CCTR(kb_qtn_rles_gd_cd) 로 잇는다(A2 — 식별자 체계는 그대로).
JB 공정가/예측은 raw 튜플 기반 jb_fair_price 모듈을 그대로 재사용.
금액 단위: CCTR 만원 → 원(×10000).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from models.complex import Area, Complex
from models.internal_kb import CctrAptTxcsHist, CctrKbAptM, CctrKbAptQtnL
from models.response_models import (
    CreditData,
    KBPrice,
    MOLITTransactions,
    NaverListings,
    PricePoint,
)
from services.real_data_service import HISTORY_DAYS, _calculate_trend

logger = logging.getLogger(__name__)


def _ymd(s: Optional[str]) -> Optional[date]:
    if not s or len(s) < 8:
        return None
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        return None


def _won(manwon) -> int:
    return int(manwon) * 10000 if manwon is not None else 0


def _empty_naver() -> NaverListings:
    return NaverListings(avg_asking=None, listing_count=0, trend="데이터 없음", history=[])


def _build_kb_from_cctr(db: Session, kb: str, pntp: Optional[str], cutoff: date) -> Optional[KBPrice]:
    q = db.query(CctrKbAptQtnL).filter(CctrKbAptQtnL.kb_qtn_rles_gd_cd == kb)
    if pntp:
        q = q.filter(CctrKbAptQtnL.pntp_seqno == pntp)
    rows = [r for r in q.all() if _ymd(r.ivst_base_dt) and _ymd(r.ivst_base_dt) >= cutoff]
    rows.sort(key=lambda r: r.ivst_base_dt)
    rows = [r for r in rows if r.deal_gnrl_txcs is not None]
    if not rows:
        return None
    history = [
        PricePoint(
            date=_ymd(r.ivst_base_dt).strftime("%Y-%m-%d"),
            price=_won(r.deal_gnrl_txcs),
            low=_won(r.deal_mnpr) or None,
            high=_won(r.deal_mxpr) or None,
        )
        for r in rows
    ]
    latest = rows[-1]
    est = _won(latest.deal_gnrl_txcs)
    return KBPrice(
        estimated=est,
        high=_won(latest.deal_mxpr) or est,
        low=_won(latest.deal_mnpr) or est,
        trend=_calculate_trend(history),
        history=history,
    )


def _build_molit_from_cctr(db: Session, kb: str, exclusive_m2: Optional[float], cutoff: date) -> Optional[MOLITTransactions]:
    rows = [
        r for r in db.query(CctrAptTxcsHist).filter(CctrAptTxcsHist.kb_qtn_rles_gd_cd == kb).all()
        if _ymd(r.tx_dt) and _ymd(r.tx_dt) >= cutoff and r.tx_amt is not None
    ]
    if exclusive_m2 is not None:
        near = [r for r in rows if r.apt_are is not None and abs(r.apt_are - exclusive_m2) <= 5.0]
        rows = near or rows
    rows.sort(key=lambda r: r.tx_dt)
    if not rows:
        return None
    history = [PricePoint(date=_ymd(r.tx_dt).strftime("%Y-%m-%d"), price=_won(r.tx_amt)) for r in rows]
    latest = rows[-1]
    return MOLITTransactions(
        recent_price=_won(latest.tx_amt),
        transaction_date=_ymd(latest.tx_dt).strftime("%Y-%m-%d"),
        trend=_calculate_trend(history),
        history=history,
    )


def _build_credit_from_cctr(db: Session, kb: str, area_obj: Optional[Area]) -> Optional[CreditData]:
    today = date.today()
    cutoff = today - timedelta(days=HISTORY_DAYS)
    pntp = area_obj.kb_area_code if area_obj else None
    exclusive = area_obj.exclusive_m2 if area_obj else None

    kb_data = _build_kb_from_cctr(db, kb, pntp, cutoff)
    if kb_data is None:
        return None
    molit_data = _build_molit_from_cctr(db, kb, exclusive, cutoff) or MOLITTransactions(
        recent_price=None, transaction_date=None, trend="데이터 없음", history=[]
    )

    # JB 공정가 — raw 튜플 기반 모듈 재사용 (build_real_credit_data 와 동일 파이프라인)
    from models.response_models import ForecastPoint as ForecastPointSchema, JBFairPriceDetail
    from services.jb_fair_price import (
        JBComputeResult,
        aggregate_monthly_series,
        compute_jb_for_month,
        compute_latest_jb,
        project_jb_forecast,
    )

    end_y, end_m = today.year, today.month
    start_y, start_m = end_y, end_m - 11
    while start_m < 1:
        start_m += 12
        start_y -= 1
    start_month, end_month = date(start_y, start_m, 1), date(end_y, end_m, 1)

    kb_raw = [
        (_ymd(r.ivst_base_dt), _won(r.deal_gnrl_txcs))
        for r in db.query(CctrKbAptQtnL).filter(
            CctrKbAptQtnL.kb_qtn_rles_gd_cd == kb,
            *([CctrKbAptQtnL.pntp_seqno == pntp] if pntp else []),
        ).all()
        if _ymd(r.ivst_base_dt) and _ymd(r.ivst_base_dt) >= start_month and r.deal_gnrl_txcs
    ]
    txn_raw = [
        (_ymd(r.tx_dt), _won(r.tx_amt))
        for r in db.query(CctrAptTxcsHist).filter(CctrAptTxcsHist.kb_qtn_rles_gd_cd == kb).all()
        if _ymd(r.tx_dt) and _ymd(r.tx_dt) >= start_month and r.tx_amt
        and (exclusive is None or (r.apt_are is not None and abs(r.apt_are - exclusive) <= 5.0))
    ]

    monthly = aggregate_monthly_series(kb_raw, txn_raw, [], start_month, end_month)
    jb_points: list[PricePoint] = []
    jb_tuples: list[tuple[int, int, int]] = []
    for agg in monthly:
        pt = compute_jb_for_month(agg)
        if pt.jb_fair_price is None:
            continue
        jb_points.append(PricePoint(date=f"{agg.year:04d}-{agg.month:02d}-01", price=pt.jb_fair_price))
        jb_tuples.append((agg.year, agg.month, pt.jb_fair_price))

    current = compute_latest_jb(monthly) or JBComputeResult(
        jb_fair_price=kb_data.estimated,
        weights={"kb": 1.0, "molit": 0.0, "naver": 0.0},
        sources={"kb": kb_data.estimated, "molit": 0, "naver": 0},
        confidence={"kb": 1.0, "molit": 0.0, "naver": 0.0},
        notes=["월별 집계 표본 부족 → KB 단일값 사용"],
    )

    forecast_schema: list[ForecastPointSchema] = []
    forecast_raw = project_jb_forecast(jb_tuples, horizon_months=12)
    if jb_tuples and forecast_raw:
        last_y, last_m, _ = jb_tuples[-1]
        for fp in forecast_raw:
            y, m = last_y, last_m + fp.month
            while m > 12:
                m -= 12
                y += 1
            forecast_schema.append(ForecastPointSchema(
                date=date(y, m, 1).strftime("%Y-%m-%d"),
                predicted=fp.predicted, lower=fp.lower, upper=fp.upper,
            ))

    return CreditData(
        kb_price=kb_data,
        molit_transactions=molit_data,
        naver_listings=_empty_naver(),
        jb_fair_price=current.jb_fair_price,
        jb_detail=JBFairPriceDetail(
            fair_price=current.jb_fair_price,
            weights=current.weights, sources=current.sources, confidence=current.confidence,
            notes=current.notes, history=jb_points, forecast=forecast_schema,
        ),
    )


def get_internal_market_data(
    db: Session,
    complex_id: Optional[int] = None,
    area_id: Optional[int] = None,
) -> dict:
    """INTERNAL_ONLY — CCTR_* 기반 시장데이터. get_real_market_data 와 동일 dict 계약.

    위경도·매물·인근동향은 CCTR_* 에 없어 None(확인 불가). 단지/평형 식별은 app-schema id 유지.
    """
    result = {"complex": None, "area": None, "credit_data": None,
              "nearby_trends": None, "price_per_pyeong": None}

    if complex_id is None:
        return result
    complex_obj = db.query(Complex).filter(Complex.id == complex_id).first()
    if not complex_obj or not complex_obj.kb_complex_id:
        return result
    result["complex"] = complex_obj

    area_obj = None
    if area_id is not None:
        area_obj = db.query(Area).filter(Area.id == area_id, Area.complex_id == complex_obj.id).first()
    result["area"] = area_obj

    # CCTR 에 이 단지가 적재됐는지 — 없으면 시세 확인 불가
    if not db.query(CctrKbAptM.kb_qtn_rles_gd_cd).filter(
        CctrKbAptM.kb_qtn_rles_gd_cd == complex_obj.kb_complex_id
    ).first():
        return result

    result["credit_data"] = _build_credit_from_cctr(db, complex_obj.kb_complex_id, area_obj)
    return result
