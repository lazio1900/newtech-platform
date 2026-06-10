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
from models.internal_kb import CctrAptTxcsHist, CctrKbAptM, CctrKbAptPntpI, CctrKbAptQtnL
from models.response_models import (
    CreditData,
    KBPrice,
    MOLITTransactions,
    NaverListings,
    PricePoint,
    PricePerPyeongPoint,
    PricePerPyeongTrend,
)
from services.real_data_service import HISTORY_DAYS, _calculate_trend, _iqr_filter

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


def _build_ppp_from_cctr(
    db: Session, target_complex: Complex, area_obj: Optional[Area]
) -> Optional[PricePerPyeongTrend]:
    """단지/읍면동/시군구 평단가 추이 — CCTR 실거래(CctrAptTxcsHist) 12개월 월별.

    외부 로직과 동일: 같은 평형대역(±5㎡) 한정, (월·단지) IQR → 월 IQR 2단계, 결측 carry-forward.
    행정구역 scope 는 Complex.dong_code/region_code → kb_complex_id 집합으로 CCTR 실거래 조회.
    """
    if not area_obj or not area_obj.exclusive_m2:
        return None
    m2_lo, m2_hi = area_obj.exclusive_m2 - 5.0, area_obj.exclusive_m2 + 5.0

    today = date.today()
    keys: list[str] = []
    cursor = today.replace(day=1)
    for _ in range(12):
        keys.append(cursor.strftime("%Y-%m"))
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    keys.reverse()
    start = date(int(keys[0][:4]), int(keys[0][5:7]), 1)

    def _kb_ids(scope_filter) -> list[str]:
        return [
            r[0] for r in db.query(Complex.kb_complex_id)
            .filter(scope_filter, Complex.kb_complex_id.isnot(None)).all()
        ]

    def _ppp(kbs: list[str]) -> dict[str, int]:
        if not kbs:
            return {}
        rows = [
            r for r in db.query(CctrAptTxcsHist).filter(
                CctrAptTxcsHist.kb_qtn_rles_gd_cd.in_(kbs),
                CctrAptTxcsHist.apt_are.isnot(None),
                CctrAptTxcsHist.tx_amt.isnot(None),
            ).all()
            if r.apt_are and m2_lo <= r.apt_are <= m2_hi and _ymd(r.tx_dt) and _ymd(r.tx_dt) >= start
        ]
        by_cm: dict[tuple[str, str], list[float]] = {}
        for r in rows:
            ym = f"{r.tx_dt[:4]}-{r.tx_dt[4:6]}"
            by_cm.setdefault((ym, r.kb_qtn_rles_gd_cd), []).append(_won(r.tx_amt) / r.apt_are)
        month_complex: dict[str, list[float]] = {}
        for (ym, _kb), vals in by_cm.items():
            kept = _iqr_filter(vals)
            if kept:
                month_complex.setdefault(ym, []).append(sum(kept) / len(kept))
        out: dict[str, int] = {}
        for ym, avgs in month_complex.items():
            kept = _iqr_filter(avgs)
            if kept:
                out[ym] = int(sum(kept) / len(kept) * 3.305785 / 10000)
        return out

    complex_d = _ppp([target_complex.kb_complex_id]) if target_complex.kb_complex_id else {}
    dong_d = _ppp(_kb_ids(Complex.dong_code == target_complex.dong_code)) if target_complex.dong_code else {}
    sigungu_d = (
        _ppp(_kb_ids(Complex.region_code.like(f"{target_complex.region_code[:5]}%")))
        if target_complex.region_code else {}
    )

    def _carry(d: dict[str, int]) -> dict[str, int]:
        out, last = {}, 0
        for k in keys:
            if k in d:
                last = d[k]
            out[k] = last
        return out

    cf, df, sf = _carry(complex_d), _carry(dong_d), _carry(sigungu_d)
    points: list[PricePerPyeongPoint] = []
    for ym in keys:
        c, dn, s = cf[ym], df[ym], sf[ym]
        c = c or dn or s
        dn = dn or s or c
        s = s or dn or c
        points.append(PricePerPyeongPoint(date=ym, complex=c, dong=dn, sigungu=s))

    if all(p.complex == 0 and p.dong == 0 and p.sigungu == 0 for p in points):
        return None
    addr = (target_complex.address or "").split()
    return PricePerPyeongTrend(
        complex_name=target_complex.name,
        dong_name=target_complex.dong_name or (addr[2] if len(addr) > 2 else "동"),
        sigungu_name=addr[1] if len(addr) > 1 else "구",
        data=points,
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
              "nearby_trends": None, "price_per_pyeong": None, "complex_master": None}

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

    # CCTR 단지 마스터 — 없으면 시세 확인 불가. 단지특성 점수용 master 도 여기서 채운다.
    cctr_m = db.query(CctrKbAptM).filter(
        CctrKbAptM.kb_qtn_rles_gd_cd == complex_obj.kb_complex_id
    ).first()
    if not cctr_m:
        return result

    # 복도구조 — 선택 평형(평형명세 FRDR_STRC_CTNT) 단위. complexes 에 컬럼 없음(정보계 원천만).
    corridor_type = None
    if area_obj and area_obj.kb_area_code:
        pr = db.query(CctrKbAptPntpI.frdr_strc_ctnt).filter(
            CctrKbAptPntpI.kb_qtn_rles_gd_cd == complex_obj.kb_complex_id,
            CctrKbAptPntpI.pntp_seqno == area_obj.kb_area_code,
        ).first()
        corridor_type = pr[0] if pr else None

    # 단지 기본정보 — CCTR(정보계 원천) 우선, dev 미배선분은 app-schema complexes 폴백.
    result["complex_master"] = {
        "total_households": cctr_m.tot_gen_cnt if cctr_m.tot_gen_cnt is not None else complex_obj.total_households,
        "total_buildings": cctr_m.tot_dong_cnt if cctr_m.tot_dong_cnt is not None else complex_obj.total_buildings,
        "max_floor": cctr_m.hscm_hgst_flr if cctr_m.hscm_hgst_flr is not None else complex_obj.max_floor,
        "total_parking": cctr_m.prkn_tcnt if cctr_m.prkn_tcnt is not None else complex_obj.total_parking,
        "built_year": cctr_m.cmcn_ym or complex_obj.built_year,
        "apst_yncd": cctr_m.apst_yncd,  # complexes 에 컬럼 없음 — 정보계 원천에서만
        "corridor_type": corridor_type,  # 평형명세 복도구조
    }

    result["credit_data"] = _build_credit_from_cctr(db, complex_obj.kb_complex_id, area_obj)

    # 유사 단지 비교 — 법정동/시군구 + 평형/연식/규모/시세 (좌표 없음)
    from services.internal_nearby_service import build_internal_nearby
    result["nearby_trends"] = build_internal_nearby(db, complex_obj, area_obj)

    # 평단가 추이 — CCTR 실거래 기반 단지/동/시군구 12개월
    result["price_per_pyeong"] = _build_ppp_from_cctr(db, complex_obj, area_obj)
    return result
