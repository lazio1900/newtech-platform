"""
실 수집 데이터 조회 서비스

DB에 저장된 KB 시세/실거래/매물 데이터를 조회하여
상세 심사(분석)에 사용할 수 있는 응답 모델로 변환한다.
데이터가 없으면 None을 반환하여 호출측에서 더미 폴백을 사용하도록 한다.
"""

import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from models.complex import Complex, Area
from models.price_data import KBPrice as KBPriceModel, Transaction, Listing, ListingStatus
from models.response_models import (
    CreditData,
    KBPrice,
    MOLITTransactions,
    NaverListings,
    PricePoint,
    NearbyPropertyTrends,
    SimilarProperty,
    PricePerPyeongTrend,
    PricePerPyeongPoint,
)

logger = logging.getLogger(__name__)

HISTORY_DAYS = 365  # 최근 12개월 (거래 빈도 낮은 단지 고려)


# ──────────────────────────────────────────────
# 1. 주소 → Complex 매칭
# ──────────────────────────────────────────────

# 지역명 블랙리스트 — 단지명으로 인정 안 함 (단지명에 우연히 포함된 광역명 매칭 차단)
_LOCATION_BLACKLIST = {
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
    "강남", "강북", "강동", "강서", "관악", "광진", "구로", "금천", "노원",
    "도봉", "동대문", "동작", "마포", "서대문", "서초", "성동", "성북", "송파",
    "양천", "영등포", "용산", "은평", "종로", "중구", "중랑",
}

_ADDR_SUFFIXES = ("시", "도", "구", "동", "읍", "면", "리", "로", "길")


def _iqr_filter(values: list[float], k: float = 1.5) -> list[float]:
    """IQR k× 아웃라이어 제거. 표본 4건 미만은 필터 의미 없어 그대로 반환."""
    n = len(values)
    if n < 4:
        return values
    sv = sorted(values)
    # 단순 중앙값 기반 사분위 (linear interpolation 생략 — 정밀도 충분)
    q1 = sv[n // 4]
    q3 = sv[(3 * n) // 4]
    iqr = q3 - q1
    if iqr <= 0:
        return values
    lo = q1 - k * iqr
    hi = q3 + k * iqr
    return [v for v in values if lo <= v <= hi]


def _last_meaningful_token(tokens: list) -> str:
    """입력 토큰들 중 동·호·번지 같은 마커 제외하고 마지막 의미있는 토큰 반환."""
    skip_re = re.compile(r"^[\d\-]+(동|호|층|번지)?$|^\d+$")
    for t in reversed(tokens):
        if skip_re.match(t):
            continue
        if t.endswith(_ADDR_SUFFIXES) and len(t) <= 3:
            continue
        return t
    return tokens[-1] if tokens else ""


def resolve_complex(db: Session, property_address: str) -> Optional[Complex]:
    """
    property_address를 Complex 레코드에 매칭한다.

    엄격 규칙:
      - 단지명이 입력의 의미있는 토큰 중 하나와 prefix/exact로 일치할 때만 매칭
      - 광역명("서울", "강남" 등)은 단지명으로 인정 안 함 (블랙리스트)
      - 단지명 길이 2 미만은 매칭 안 함
    """
    addr = property_address.strip()
    if not addr:
        return None

    # 1단계: 정확 매칭
    exact = db.query(Complex).filter(Complex.address == addr).first()
    if exact:
        logger.info(f"[resolve] 정확 매칭: {exact.name} (id={exact.id})")
        return exact

    # 토큰 분리 + 의미있는 토큰만
    tokens = [t for t in addr.replace(",", " ").split() if len(t) >= 2]
    meaningful_tokens = [
        t for t in tokens
        if not (t.endswith(_ADDR_SUFFIXES) and len(t) <= 3)
        and t not in _LOCATION_BLACKLIST
    ]
    if not meaningful_tokens:
        return None

    last_token = _last_meaningful_token(tokens)

    # 2단계: 단지명 후보 조회 — 마지막 의미 토큰의 prefix 일치 단지 우선
    from sqlalchemy import literal

    name_conditions = []
    # 역방향: 단지명 ⊂ 입력주소
    name_conditions.append(literal(addr).ilike(func.concat("%", Complex.name, "%")))
    # 정방향: 입력 의미 토큰이 단지명에 포함
    for tok in meaningful_tokens:
        name_conditions.append(Complex.name.ilike(f"%{tok}%"))

    candidates = db.query(Complex).filter(or_(*name_conditions)).all()
    logger.info(
        f"[resolve] 주소='{addr}' last_token='{last_token}' → 후보 {len(candidates)}개"
    )

    if not candidates:
        return None

    # 3단계: 점수 기반 최적 후보 선택
    def score(c: Complex) -> int:
        name = (c.name or "").strip()
        if len(name) < 2 or name in _LOCATION_BLACKLIST:
            return -1

        s = 0

        # (a) 단지명이 마지막 의미 토큰의 prefix → 가장 강력
        if last_token and last_token.startswith(name):
            s += 100 + len(name) * 5
        # (b) 단지명이 마지막 토큰 자체 (정확 일치, 광역명 제외했으니 안전)
        elif name == last_token:
            s += 80 + len(name) * 5
        # (c) 단지명이 입력 주소에 substring (단어 경계 무시)
        elif name in addr:
            s += 30 + len(name) * 2

        # (d) 의미 토큰 중 단지명에 포함되는 것 가산
        for tok in meaningful_tokens:
            if tok != name and tok in name:
                s += len(tok)

        return s

    candidates.sort(key=score, reverse=True)
    best = candidates[0]
    best_score = score(best)

    MIN_SCORE = 30  # (c) 이상이어야 인정
    if best_score < MIN_SCORE:
        logger.info(f"[resolve] 점수 미달 ({best_score} < {MIN_SCORE}) → 매칭 실패")
        return None

    logger.info(f"[resolve] 최적 매칭: {best.name} (id={best.id}, score={best_score})")
    return best


# ──────────────────────────────────────────────
# 2. 면적 매칭
# ──────────────────────────────────────────────

def resolve_area(
    db: Session,
    complex_obj: Complex,
    target_pyeong: Optional[int] = None,
) -> Optional[Area]:
    """
    Complex 내에서 가장 적합한 Area를 선택한다.
    target_pyeong이 주어지면 가장 가까운 평형을 선택하고,
    없으면 KB 시세 데이터가 가장 많은 면적을 선택한다.
    """
    areas = complex_obj.areas
    if not areas:
        return None

    if target_pyeong:
        def distance(a: Area) -> float:
            if a.pyeong:
                return abs(a.pyeong - target_pyeong)
            return abs(a.exclusive_m2 / 3.305785 - target_pyeong)

        return min(areas, key=distance)

    # 기본값: KB 시세 레코드가 가장 많은 면적
    best = None
    best_count = -1
    for a in areas:
        count = (
            db.query(func.count(KBPriceModel.id))
            .filter(KBPriceModel.area_id == a.id)
            .scalar()
        ) or 0
        if count > best_count:
            best_count = count
            best = a

    return best or areas[0]


# ──────────────────────────────────────────────
# 3. 시세 데이터 (CreditData)
# ──────────────────────────────────────────────

def build_real_credit_data(
    db: Session,
    complex_obj: Complex,
    area_obj: Area,
) -> Optional[CreditData]:
    """
    DB의 실 데이터로 CreditData를 구성한다.
    KB 시세가 없으면 None을 반환한다.
    """
    today = date.today()
    cutoff = today - timedelta(days=HISTORY_DAYS)

    kb_data = _build_kb_price(db, complex_obj.id, area_obj.id, cutoff)
    molit_data = _build_molit_transactions(
        db, complex_obj.id, area_obj.exclusive_m2, cutoff
    )
    naver_data = _build_naver_listings(db, complex_obj.id, area_obj.exclusive_m2, cutoff)

    if kb_data is None:
        return None

    if molit_data is None:
        molit_data = MOLITTransactions(
            recent_price=None,
            transaction_date=None,
            trend="데이터 없음",
            history=[],
        )

    if naver_data is None:
        naver_data = NaverListings(
            avg_asking=None,
            listing_count=0,
            trend="데이터 없음",
            history=[],
        )

    # JB 적정시세 — 월별 IQR 평균 집계 + 동적 가중치 + OLS 예측
    from services.jb_fair_price import (
        aggregate_monthly_series,
        compute_jb_for_month,
        compute_latest_jb,
        project_jb_forecast,
    )
    from models.response_models import JBFairPriceDetail, ForecastPoint as ForecastPointSchema

    # 12M 격자 (이번 달 포함, 직전 11개월부터)
    end_month_year, end_month_mon = today.year, today.month
    start_month_year, start_month_mon = end_month_year, end_month_mon - 11
    while start_month_mon < 1:
        start_month_mon += 12
        start_month_year -= 1
    start_month = date(start_month_year, start_month_mon, 1)
    end_month = date(end_month_year, end_month_mon, 1)

    # raw 데이터 재조회 — 월별 집계용
    kb_rows = (
        db.query(KBPriceModel.as_of_date, KBPriceModel.general_price)
        .filter(
            KBPriceModel.complex_id == complex_obj.id,
            KBPriceModel.area_id == area_obj.id,
            KBPriceModel.as_of_date >= start_month,
        )
        .all()
    )
    kb_raw = [(r[0], r[1]) for r in kb_rows if r[1]]

    txn_rows = (
        db.query(Transaction.contract_date, Transaction.price)
        .filter(
            Transaction.complex_id == complex_obj.id,
            Transaction.contract_date >= start_month,
            Transaction.is_cancelled == False,
            Transaction.exclusive_m2.between(
                area_obj.exclusive_m2 - 5.0,
                area_obj.exclusive_m2 + 5.0,
            ),
        )
        .all()
    )
    txn_raw = [(r[0], r[1]) for r in txn_rows]

    # 호가 — status 와 무관히 posted_at 기준 (closed 매물도 그 월에 살아있었던 것이면 반영).
    # 매매 거래유형만, 면적 ±5㎡ 톨러런스.
    listing_rows = (
        db.query(Listing.posted_at, Listing.status_updated_at, Listing.ask_price)
        .filter(
            Listing.complex_id == complex_obj.id,
            Listing.ask_price.isnot(None),
            Listing.trade_type == "매매",
            Listing.exclusive_m2.between(
                area_obj.exclusive_m2 - 5.0,
                area_obj.exclusive_m2 + 5.0,
            ),
        )
        .all()
    )
    listing_raw: list[tuple[date, Optional[date], int]] = []
    for posted, status_upd, price in listing_rows:
        if posted is None:
            continue
        p_d = posted.date() if hasattr(posted, "date") else posted
        s_d = status_upd.date() if status_upd and hasattr(status_upd, "date") else status_upd
        listing_raw.append((p_d, s_d, price))

    # 월별 집계 → 월별 JB 산출 → history
    monthly = aggregate_monthly_series(kb_raw, txn_raw, listing_raw, start_month, end_month)

    jb_history_points: list[PricePoint] = []
    jb_history_tuples: list[tuple[int, int, int]] = []
    for agg in monthly:
        pt = compute_jb_for_month(agg)
        if pt.jb_fair_price is None:
            continue
        d_str = f"{agg.year:04d}-{agg.month:02d}-01"
        jb_history_points.append(PricePoint(date=d_str, price=pt.jb_fair_price))
        jb_history_tuples.append((agg.year, agg.month, pt.jb_fair_price))

    # 현 시점 JB — 마지막 산출 가능한 월
    current = compute_latest_jb(monthly)
    if current is None:
        # 폴백: 모든 월 데이터가 부족하면 KB 단일값
        from services.jb_fair_price import JBComputeResult
        current = JBComputeResult(
            jb_fair_price=kb_data.estimated,
            weights={"kb": 1.0, "molit": 0.0, "naver": 0.0},
            sources={"kb": kb_data.estimated, "molit": 0, "naver": 0},
            confidence={"kb": 1.0, "molit": 0.0, "naver": 0.0},
            notes=["월별 집계 표본 부족 → KB 단일값 사용"],
        )

    # 예측 — OLS 로그-선형 회귀
    forecast_raw = project_jb_forecast(jb_history_tuples, horizon_months=12)
    forecast_schema: list[ForecastPointSchema] = []
    if jb_history_tuples and forecast_raw:
        last_y, last_m, _ = jb_history_tuples[-1]
        for fp in forecast_raw:
            y, m = last_y, last_m + fp.month
            while m > 12:
                m -= 12
                y += 1
            forecast_schema.append(ForecastPointSchema(
                date=date(y, m, 1).strftime("%Y-%m-%d"),
                predicted=fp.predicted,
                lower=fp.lower,
                upper=fp.upper,
            ))

    return CreditData(
        kb_price=kb_data,
        molit_transactions=molit_data,
        naver_listings=naver_data,
        jb_fair_price=current.jb_fair_price,
        jb_detail=JBFairPriceDetail(
            fair_price=current.jb_fair_price,
            weights=current.weights,
            sources=current.sources,
            confidence=current.confidence,
            notes=current.notes,
            history=jb_history_points,
            forecast=forecast_schema,
        ),
    )


def _build_kb_price(
    db: Session,
    complex_id: int,
    area_id: int,
    cutoff: date,
) -> Optional[KBPrice]:
    """KBPrice 테이블에서 최근 90일 시세를 조회한다."""
    prices = (
        db.query(KBPriceModel)
        .filter(
            KBPriceModel.complex_id == complex_id,
            KBPriceModel.area_id == area_id,
            KBPriceModel.as_of_date >= cutoff,
        )
        .order_by(KBPriceModel.as_of_date.asc())
        .all()
    )

    if not prices:
        return None

    latest = prices[-1]

    history = [
        PricePoint(
            date=p.as_of_date.strftime("%Y-%m-%d"),
            price=p.general_price or 0,
            low=p.low_avg_price,
            high=p.high_avg_price,
        )
        for p in prices
        if p.general_price is not None
    ]

    trend = _calculate_trend(history)

    return KBPrice(
        estimated=latest.general_price or 0,
        high=latest.high_avg_price or (latest.general_price or 0),
        low=latest.low_avg_price or (latest.general_price or 0),
        trend=trend,
        history=history,
    )


def _build_molit_transactions(
    db: Session,
    complex_id: int,
    exclusive_m2: float,
    cutoff: date,
) -> Optional[MOLITTransactions]:
    """Transaction 테이블에서 최근 90일 실거래를 조회한다."""
    m2_tolerance = 5.0

    txns = (
        db.query(Transaction)
        .filter(
            Transaction.complex_id == complex_id,
            Transaction.contract_date >= cutoff,
            Transaction.is_cancelled == False,
            Transaction.exclusive_m2.between(
                exclusive_m2 - m2_tolerance,
                exclusive_m2 + m2_tolerance,
            ),
        )
        .order_by(Transaction.contract_date.asc())
        .all()
    )

    # 유사 면적 데이터 없으면 면적 필터 없이 재조회
    if not txns:
        txns = (
            db.query(Transaction)
            .filter(
                Transaction.complex_id == complex_id,
                Transaction.contract_date >= cutoff,
                Transaction.is_cancelled == False,
            )
            .order_by(Transaction.contract_date.asc())
            .all()
        )

    if not txns:
        return None

    latest = txns[-1]

    history = [
        PricePoint(
            date=t.contract_date.strftime("%Y-%m-%d"),
            price=t.price,
        )
        for t in txns
    ]

    trend = _calculate_trend(history)

    return MOLITTransactions(
        recent_price=latest.price,
        transaction_date=latest.contract_date.strftime("%Y-%m-%d"),
        trend=trend,
        history=history,
    )


def _build_naver_listings(
    db: Session,
    complex_id: int,
    exclusive_m2: float,
    cutoff: date,
) -> Optional[NaverListings]:
    """Listing 테이블에서 현재 매물 및 호가 추이를 조회한다.

    history 는 매물의 등록일(posted_at) 기준 산점도. 매물별 1포인트.
    면적은 transactions 와 동일하게 ±5㎡ 톨러런스로 필터.
    """
    m2_tolerance = 5.0
    m2_lo, m2_hi = exclusive_m2 - m2_tolerance, exclusive_m2 + m2_tolerance

    active_listings = (
        db.query(Listing)
        .filter(
            Listing.complex_id == complex_id,
            Listing.status == ListingStatus.ACTIVE,
            Listing.trade_type == "매매",
            Listing.exclusive_m2.between(m2_lo, m2_hi),
        )
        .all()
    )

    all_listings = (
        db.query(Listing)
        .filter(
            Listing.complex_id == complex_id,
            Listing.trade_type == "매매",
            Listing.exclusive_m2.between(m2_lo, m2_hi),
            # posted_at 우선 — 없으면 fetched_at 으로 fallback
            (Listing.posted_at >= cutoff) | (Listing.fetched_at >= cutoff),
        )
        .all()
    )

    if not active_listings and not all_listings:
        return None

    listing_count = len(active_listings)
    # 가장 최근 등록(posted_at) active 매물의 호가
    latest_asking = 0
    pool = active_listings or all_listings
    if pool:
        latest_listing = max(
            pool,
            key=lambda l: l.posted_at or l.fetched_at or datetime.min,
        )
        latest_asking = latest_listing.ask_price or 0
    avg_asking = latest_asking

    # 호가 추이 — 매물별 (posted_at, ask_price) 1포인트씩 산점도용
    points: list[tuple[date, int]] = []
    for l in all_listings:
        anchor = l.posted_at or l.fetched_at
        if anchor and l.ask_price:
            points.append((anchor.date() if hasattr(anchor, "date") else anchor, l.ask_price))
    points.sort(key=lambda x: x[0])

    history = [
        PricePoint(date=d.strftime("%Y-%m-%d"), price=p)
        for d, p in points
    ]

    trend = _calculate_listing_trend(listing_count)

    return NaverListings(
        avg_asking=avg_asking,
        listing_count=listing_count,
        trend=trend,
        history=history,
    )


# ──────────────────────────────────────────────
# 4. 인근 유사 물건지 동향
# ──────────────────────────────────────────────

def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    """두 좌표 간 직선 거리 (m)."""
    import math
    R = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return int(R * c)


def build_real_nearby_trends(
    db: Session,
    target_complex: Complex,
    target_area: Optional[Area],
    max_count: int = 5,
) -> Optional[NearbyPropertyTrends]:
    """반경 + 평형 매칭 + 유사도 점수 기반 인근 유사 물건 산출.

    1) 타겟 lat/lng 기준 단계적 반경/평형 확장으로 후보 모음
    2) 후보별 최근 거래가 사전 조회 (가격 유사도 점수에 필요)
    3) 유사도 점수 (5요소):
         - 거리 30% (0m=1.0, 2km=0.0)
         - 평형 25% (±0=1.0, ±15㎡=0.0)
         - 가격 25% (±0%=1.0, ±50%=0.0; 타겟 가격 미상이면 모든 후보 0.5 중립)
         - 년식 15% (±0=1.0, ±20년=0.0)
         - 세대수 5% (min/max 비율)
    4) 점수 상위 max_count 건
    5) 가격차 % = (유사 - 타겟) / 타겟
    """
    if not target_complex.region_code:
        return None
    target_lat = target_complex.lat
    target_lng = target_complex.lng
    if target_lat is None or target_lng is None:
        return None

    target_m2 = target_area.exclusive_m2 if target_area else None
    target_age = None
    if target_complex.built_year:
        try:
            target_age = date.today().year - int(str(target_complex.built_year)[:4])
        except (ValueError, TypeError):
            pass
    target_units = target_complex.total_households or 0

    today = date.today()
    cutoff_3m = today - timedelta(days=90)

    # 타겟 최근 거래가 (비교 기준)
    target_recent = (
        db.query(Transaction)
        .filter(
            Transaction.complex_id == target_complex.id,
            Transaction.is_cancelled == False,
        )
        .order_by(Transaction.contract_date.desc())
        .first()
    )
    target_recent_price = target_recent.price if target_recent else None

    # 단계적 반경/평형 확장 — (radius_m, m2_tolerance)
    plans = [(1000, 5.0), (1000, 10.0), (2000, 10.0), (2000, 15.0)]
    candidates: list[tuple[Complex, Area, int]] = []  # (complex, matched_area, distance_m)

    for radius, m2_tol in plans:
        candidates = []
        # 시군구 후보 (lat/lng 있는 것만)
        nearby = (
            db.query(Complex)
            .filter(
                Complex.region_code.like(f"{target_complex.region_code[:5]}%"),
                Complex.id != target_complex.id,
                Complex.is_active == True,
                Complex.lat.isnot(None),
                Complex.lng.isnot(None),
            )
            .all()
        )
        for c in nearby:
            d = _haversine_m(target_lat, target_lng, c.lat, c.lng)
            if d > radius:
                continue
            # 평형 매칭 area 찾기
            matched_area = None
            if target_m2 and c.areas:
                for a in c.areas:
                    if a.exclusive_m2 and abs(a.exclusive_m2 - target_m2) <= m2_tol:
                        if matched_area is None or abs(a.exclusive_m2 - target_m2) < abs((matched_area.exclusive_m2 or 0) - target_m2):
                            matched_area = a
            elif c.areas:
                matched_area = c.areas[0]
            if matched_area is None:
                continue
            candidates.append((c, matched_area, d))
        if len(candidates) >= max_count:
            break

    if not candidates:
        return None

    # 후보별 최근/오래된 거래 사전 조회 (가격 유사도 점수 + 결과 빌드 양쪽에 사용)
    enriched: list[tuple[Complex, Area, int, Transaction, Optional[Transaction]]] = []
    for c, a, d in candidates:
        m2_lo = (a.exclusive_m2 or 0) - 5.0
        m2_hi = (a.exclusive_m2 or 0) + 5.0
        recent_txn = (
            db.query(Transaction)
            .filter(
                Transaction.complex_id == c.id,
                Transaction.is_cancelled == False,
                Transaction.exclusive_m2.between(m2_lo, m2_hi),
            )
            .order_by(Transaction.contract_date.desc())
            .first()
        )
        if not recent_txn:
            recent_txn = (
                db.query(Transaction)
                .filter(Transaction.complex_id == c.id, Transaction.is_cancelled == False)
                .order_by(Transaction.contract_date.desc())
                .first()
            )
        if not recent_txn:
            continue  # 가격 정보 자체 없음 → 후보에서 제외
        oldest_txn = (
            db.query(Transaction)
            .filter(
                Transaction.complex_id == c.id,
                Transaction.contract_date >= cutoff_3m,
                Transaction.is_cancelled == False,
                Transaction.exclusive_m2.between(m2_lo, m2_hi),
            )
            .order_by(Transaction.contract_date.asc())
            .first()
        )
        enriched.append((c, a, d, recent_txn, oldest_txn))

    if not enriched:
        return None

    # 5요소 유사도 점수
    def score(c: Complex, a: Area, d: int, recent_txn: Transaction) -> float:
        # 거리 30% (0m=1.0, 2km=0.0)
        s_d = max(0.0, 1.0 - d / 2000.0)
        # 평형 25% (±0=1.0, ±15㎡=0.0)
        s_a = 1.0
        if target_m2 and a.exclusive_m2:
            s_a = max(0.0, 1.0 - abs(a.exclusive_m2 - target_m2) / 15.0)
        # 가격 25% (±0%=1.0, ±50%=0.0). 타겟 가격 미상이면 0.5 중립
        if target_recent_price and target_recent_price > 0:
            diff_ratio = abs(recent_txn.price - target_recent_price) / target_recent_price
            s_p = max(0.0, 1.0 - diff_ratio / 0.50)
        else:
            s_p = 0.5
        # 년식 15% (±0=1.0, ±20년=0.0)
        s_y = 1.0
        if target_age is not None and c.built_year:
            try:
                c_age = today.year - int(str(c.built_year)[:4])
                s_y = max(0.0, 1.0 - abs(c_age - target_age) / 20.0)
            except (ValueError, TypeError):
                pass
        # 세대수 5% (min/max 비율)
        s_u = 1.0
        if target_units > 0 and c.total_households:
            ratio = min(target_units, c.total_households) / max(target_units, c.total_households)
            s_u = ratio
        return round(s_d * 0.30 + s_a * 0.25 + s_p * 0.25 + s_y * 0.15 + s_u * 0.05, 3)

    scored: list[tuple[Complex, Area, int, Transaction, Optional[Transaction], float]] = []
    for c, a, d, recent_txn, oldest_txn in enriched:
        scored.append((c, a, d, recent_txn, oldest_txn, score(c, a, d, recent_txn)))
    scored.sort(key=lambda x: x[5], reverse=True)
    scored = scored[:max_count]

    similar_properties: List[SimilarProperty] = []
    change_rates: list[float] = []
    for c, a, d, recent_txn, oldest_txn, sim in scored:
        price_change_rate = 0.0
        if oldest_txn and oldest_txn.price > 0 and oldest_txn.id != recent_txn.id:
            price_change_rate = round((recent_txn.price - oldest_txn.price) / oldest_txn.price, 3)
        change_rates.append(price_change_rate)

        price_diff_pct = None
        if target_recent_price and target_recent_price > 0:
            price_diff_pct = round((recent_txn.price - target_recent_price) / target_recent_price * 100, 1)

        parts = (c.address or "").split()
        sido = parts[0] if len(parts) > 0 else ""
        sigungu = parts[1] if len(parts) > 1 else ""
        c_age = 0
        if c.built_year:
            try:
                c_age = today.year - int(str(c.built_year)[:4])
            except (ValueError, TypeError):
                pass

        similar_properties.append(SimilarProperty(
            name=c.name,
            sido=sido,
            sigungu=sigungu,
            address=c.address or "",
            units=c.total_households or 0,
            age=c_age,
            area=int(a.pyeong) if a.pyeong else (int((a.exclusive_m2 or 0) / 3.305785) if a.exclusive_m2 else 0),
            exclusive_m2=a.exclusive_m2,
            lat=c.lat,
            lng=c.lng,
            distance_m=d,
            similarity=sim,
            recent_price=recent_txn.price,
            price_change_rate=price_change_rate,
            price_diff_pct=price_diff_pct,
        ))

    if not similar_properties:
        return None

    avg_change = round(sum(change_rates) / len(change_rates), 3) if change_rates else 0.0
    radius_used = next((p[0] for p in plans if any(d <= p[0] for _, _, d in candidates)), 2000)

    return NearbyPropertyTrends(
        target_lat=target_lat,
        target_lng=target_lng,
        target_recent_price=target_recent_price,
        radius_m=radius_used,
        avg_change_rate=avg_change,
        similar_properties=similar_properties,
    )


# ──────────────────────────────────────────────
# 5. 평단가 추이
# ──────────────────────────────────────────────

def build_real_price_per_pyeong(
    db: Session,
    target_complex: Complex,
    target_area: Area,
) -> Optional[PricePerPyeongTrend]:
    """단지/읍면동/시군구 평단가 추이 — 실거래가 기반 12개월 월별.

    세 시리즈 모두 면적 ±5㎡ 톨러런스로 한정해 같은 평형 대역끼리 비교.
    결측 월은 직전 값 carry-forward (그 달 거래 0건이면 전월 평단가 유지).
    """
    pyeong = target_area.pyeong or (target_area.exclusive_m2 / 3.305785 if target_area.exclusive_m2 else 0)
    if pyeong <= 0 or not target_area.exclusive_m2:
        return None
    m2_lo = target_area.exclusive_m2 - 5.0
    m2_hi = target_area.exclusive_m2 + 5.0

    today = date.today()
    months_back = 12
    # 월 키 list (오래된 → 최근)
    month_keys: list[tuple[str, date, date]] = []
    cursor = today.replace(day=1)
    for _ in range(months_back):
        end = (cursor + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        end = min(end, today)
        month_keys.append((cursor.strftime("%Y-%m"), cursor, end))
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    month_keys.reverse()

    def _avg_ppp_for_scope(scope_filter) -> dict[str, int]:
        """월별 평단가 dict {YYYY-MM: ppp(만원/평)} — 단지 단위 1표 가중치 균등화.

        한 달에 한 단지에서 거래가 몰리거나, 평단가 양극단인 두 단지로 나뉘면
        거래 단위 평균은 한쪽으로 끌려간다. 따라서:
          1) (월, 단지) 별로 거래 단위 IQR 1.5× 적용 후 단지-월 평단가 산출
          2) 그 단지-월 평단가들을 다시 월 단위로 IQR 1.5× → 산술평균
        단지 scope 처럼 단지가 1개면 1단계만 의미 있음 (2단계는 1값 그대로).
        """
        rows = (
            db.query(
                func.to_char(Transaction.contract_date, 'YYYY-MM').label('ym'),
                Transaction.complex_id.label('cid'),
                (Transaction.price / Transaction.exclusive_m2).label('won_per_m2'),
            )
            .join(Complex, Transaction.complex_id == Complex.id)
            .filter(scope_filter)
            .filter(Transaction.is_cancelled == False)
            .filter(Transaction.exclusive_m2.between(m2_lo, m2_hi))
            .filter(Transaction.contract_date >= month_keys[0][1])
            .all()
        )
        # (ym, complex_id) → [ppm, ...]
        by_complex_month: dict[tuple[str, int], list[float]] = {}
        for r in rows:
            if r.won_per_m2 is None:
                continue
            by_complex_month.setdefault((r.ym, r.cid), []).append(float(r.won_per_m2))

        # 단지-월 평단가 (단지 내부 거래 IQR 제거 후 평균)
        complex_month_ppm: dict[str, list[float]] = {}
        for (ym, _cid), vals in by_complex_month.items():
            kept = _iqr_filter(vals)
            if not kept:
                continue
            complex_month_ppm.setdefault(ym, []).append(sum(kept) / len(kept))

        out: dict[str, int] = {}
        for ym, complex_avgs in complex_month_ppm.items():
            kept = _iqr_filter(complex_avgs)
            if not kept:
                continue
            avg_won_per_m2 = sum(kept) / len(kept)
            out[ym] = int(avg_won_per_m2 * 3.305785 / 10000)
        return out

    complex_dict = _avg_ppp_for_scope(Complex.id == target_complex.id)
    dong_dict = (
        _avg_ppp_for_scope(Complex.dong_code == target_complex.dong_code)
        if target_complex.dong_code else {}
    )
    sigungu_dict = (
        _avg_ppp_for_scope(Complex.region_code.like(f"{target_complex.region_code[:5]}%"))
        if target_complex.region_code else {}
    )

    # carry-forward 로 결측 채움
    def _carry_forward(d: dict[str, int]) -> dict[str, int]:
        out = {}
        last = 0
        for k, _, _ in month_keys:
            if k in d:
                last = d[k]
                out[k] = last
            elif last > 0:
                out[k] = last
            else:
                out[k] = 0
        return out

    complex_filled = _carry_forward(complex_dict)
    dong_filled = _carry_forward(dong_dict)
    sigungu_filled = _carry_forward(sigungu_dict)

    data_points: List[PricePerPyeongPoint] = []
    for ym, _, _ in month_keys:
        c_ppp = complex_filled.get(ym, 0)
        d_ppp = dong_filled.get(ym, 0)
        s_ppp = sigungu_filled.get(ym, 0)
        # 단지 데이터 없으면 동값 fallback, 동도 없으면 시군구
        if c_ppp == 0:
            c_ppp = d_ppp or s_ppp
        if d_ppp == 0:
            d_ppp = s_ppp or c_ppp
        if s_ppp == 0:
            s_ppp = d_ppp or c_ppp
        data_points.append(PricePerPyeongPoint(
            date=ym, complex=c_ppp, dong=d_ppp, sigungu=s_ppp,
        ))

    if all(p.complex == 0 and p.dong == 0 and p.sigungu == 0 for p in data_points):
        return None

    address_parts = (target_complex.address or "").split()
    dong_name = target_complex.dong_name or (address_parts[2] if len(address_parts) > 2 else "동")
    sigungu_name = address_parts[1] if len(address_parts) > 1 else "구"

    return PricePerPyeongTrend(
        complex_name=target_complex.name,
        dong_name=dong_name,
        sigungu_name=sigungu_name,
        data=data_points,
    )


# ──────────────────────────────────────────────
# 6. 트렌드 계산 헬퍼
# ──────────────────────────────────────────────

def _calculate_trend(history: List[PricePoint]) -> str:
    """가격 히스토리에서 추세를 판단한다."""
    if len(history) < 2:
        return "데이터 부족"

    first_price = history[0].price
    last_price = history[-1].price

    if first_price == 0:
        return "데이터 부족"

    change_pct = (last_price - first_price) / first_price * 100

    if change_pct > 3:
        return "상승세"
    elif change_pct < -3:
        return "하락세"
    else:
        return "안정적"


def _calculate_listing_trend(listing_count: int) -> str:
    """매물 수로 활동 추세를 판단한다."""
    if listing_count >= 20:
        return "활발"
    elif listing_count >= 5:
        return "보통"
    else:
        return "저조"


# ──────────────────────────────────────────────
# 7. 오케스트레이터
# ──────────────────────────────────────────────

def get_real_market_data(
    db: Session,
    property_address: str,
    target_pyeong: Optional[int] = None,
    complex_id: Optional[int] = None,
    area_id: Optional[int] = None,
) -> dict:
    """
    실 수집 데이터를 종합적으로 조회한다.

    매칭 우선순위:
      1) complex_id 가 주어지면 그 단지를 직접 조회 (가장 정확)
      2) area_id 가 주어지면 그 평형을 직접 사용
      3) 둘 다 없으면 property_address 로 fuzzy 매칭

    반환값:
        {complex, area, credit_data, nearby_trends, price_per_pyeong}.
    각 값이 None이면 호출측에서 더미 데이터로 폴백한다.
    """
    result = {
        "complex": None,
        "area": None,
        "credit_data": None,
        "nearby_trends": None,
        "price_per_pyeong": None,
    }

    complex_obj: Optional[Complex] = None

    # 1) ID 기반 직접 조회
    if complex_id is not None:
        complex_obj = db.query(Complex).filter(Complex.id == complex_id).first()
        if complex_obj:
            logger.info(f"[real_data] complex_id={complex_id} → {complex_obj.name}")
        else:
            logger.warning(f"[real_data] complex_id={complex_id} not found in DB")

    # 2) ID 매칭 실패 또는 미제공 시 주소 기반 fuzzy
    if not complex_obj:
        complex_obj = resolve_complex(db, property_address)

    if not complex_obj:
        logger.info(f"No complex found for address: {property_address}")
        return result

    result["complex"] = complex_obj

    # area: ID 우선
    area_obj: Optional[Area] = None
    if area_id is not None:
        area_obj = (
            db.query(Area)
            .filter(Area.id == area_id, Area.complex_id == complex_obj.id)
            .first()
        )
    if not area_obj:
        area_obj = resolve_area(db, complex_obj, target_pyeong)
    result["area"] = area_obj

    if area_obj:
        result["credit_data"] = build_real_credit_data(db, complex_obj, area_obj)
        result["price_per_pyeong"] = build_real_price_per_pyeong(
            db, complex_obj, area_obj
        )

    fallback_area = area_obj or (complex_obj.areas[0] if complex_obj.areas else None)
    result["nearby_trends"] = build_real_nearby_trends(
        db, complex_obj, fallback_area
    )

    return result
