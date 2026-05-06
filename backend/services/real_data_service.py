"""
실 수집 데이터 조회 서비스

DB에 저장된 KB 시세/실거래/매물 데이터를 조회하여
상세 심사(분석)에 사용할 수 있는 응답 모델로 변환한다.
데이터가 없으면 None을 반환하여 호출측에서 더미 폴백을 사용하도록 한다.
"""

import logging
import re
from datetime import date, timedelta
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

HISTORY_DAYS = 90  # 최근 3개월


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
    naver_data = _build_naver_listings(db, complex_obj.id, cutoff)

    if kb_data is None:
        return None

    if molit_data is None:
        molit_data = MOLITTransactions(
            recent_price=kb_data.estimated,
            transaction_date=today.strftime("%Y-%m-%d"),
            trend="데이터 부족",
            history=[],
        )

    if naver_data is None:
        naver_data = NaverListings(
            avg_asking=kb_data.estimated,
            listing_count=0,
            trend="데이터 부족",
            history=[],
        )

    return CreditData(
        kb_price=kb_data,
        molit_transactions=molit_data,
        naver_listings=naver_data,
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
    cutoff: date,
) -> Optional[NaverListings]:
    """Listing 테이블에서 현재 매물 및 최근 90일 호가를 조회한다."""
    active_listings = (
        db.query(Listing)
        .filter(
            Listing.complex_id == complex_id,
            Listing.status == ListingStatus.ACTIVE,
        )
        .all()
    )

    all_listings = (
        db.query(Listing)
        .filter(
            Listing.complex_id == complex_id,
            Listing.fetched_at >= cutoff,
        )
        .order_by(Listing.fetched_at.asc())
        .all()
    )

    if not active_listings and not all_listings:
        return None

    listing_count = len(active_listings)
    avg_asking = 0
    if active_listings:
        avg_asking = int(
            sum(l.ask_price for l in active_listings) / len(active_listings)
        )

    # 일별 평균 호가 히스토리
    daily_prices: dict[str, list[int]] = {}
    for l in all_listings:
        if l.fetched_at:
            day_key = l.fetched_at.strftime("%Y-%m-%d")
            daily_prices.setdefault(day_key, []).append(l.ask_price)

    history = [
        PricePoint(date=d, price=int(sum(ps) / len(ps)))
        for d, ps in sorted(daily_prices.items())
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

def build_real_nearby_trends(
    db: Session,
    target_complex: Complex,
    target_area: Optional[Area],
    max_count: int = 5,
) -> Optional[NearbyPropertyTrends]:
    """
    같은 시군구(region_code 앞 5자리)의 다른 단지들에서
    최근 거래 정보를 가져와 유사 물건지 동향을 구성한다.
    """
    if not target_complex.region_code:
        return None

    cutoff = date.today() - timedelta(days=HISTORY_DAYS)
    region_prefix = target_complex.region_code[:5]

    nearby = (
        db.query(Complex)
        .filter(
            Complex.region_code.like(f"{region_prefix}%"),
            Complex.id != target_complex.id,
            Complex.is_active == True,
        )
        .limit(max_count * 3)
        .all()
    )

    if not nearby:
        return None

    similar_properties: List[SimilarProperty] = []
    for c in nearby:
        if len(similar_properties) >= max_count:
            break

        recent_txn = (
            db.query(Transaction)
            .filter(
                Transaction.complex_id == c.id,
                Transaction.is_cancelled == False,
            )
            .order_by(Transaction.contract_date.desc())
            .first()
        )

        if not recent_txn:
            continue

        oldest_txn = (
            db.query(Transaction)
            .filter(
                Transaction.complex_id == c.id,
                Transaction.contract_date >= cutoff,
                Transaction.is_cancelled == False,
            )
            .order_by(Transaction.contract_date.asc())
            .first()
        )

        price_change_rate = 0.0
        if oldest_txn and oldest_txn.price > 0:
            price_change_rate = round(
                (recent_txn.price - oldest_txn.price) / oldest_txn.price, 3
            )

        c_area = c.areas[0] if c.areas else None
        area_pyeong = int(c_area.pyeong) if c_area and c_area.pyeong else 0

        parts = (c.address or "").split()
        sido = parts[0] if len(parts) > 0 else ""
        sigungu = parts[1] if len(parts) > 1 else ""

        sim_units = c.total_households or 0
        sim_age = 0
        if c.built_year:
            try:
                sim_age = date.today().year - int(str(c.built_year)[:4])
            except (ValueError, TypeError):
                sim_age = 0

        similar_properties.append(
            SimilarProperty(
                name=c.name,
                sido=sido,
                sigungu=sigungu,
                address=c.address or "",
                units=sim_units,
                age=sim_age,
                area=area_pyeong,
                lat=0.0,
                lng=0.0,
                recent_price=recent_txn.price,
                price_change_rate=price_change_rate,
            )
        )

    if not similar_properties:
        return None

    return NearbyPropertyTrends(
        target_lat=0.0,
        target_lng=0.0,
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
    """
    KB 시세와 면적 정보를 이용해 단지/읍면동/시군구 평단가 추이를 계산한다.
    """
    pyeong = target_area.pyeong or (target_area.exclusive_m2 / 3.305785)
    if pyeong <= 0:
        return None

    today = date.today()
    data_points: List[PricePerPyeongPoint] = []

    for months_ago in range(2, -1, -1):
        month_start = (today.replace(day=1) - timedelta(days=months_ago * 30)).replace(day=1)
        if months_ago > 0:
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        else:
            month_end = today

        month_str = month_start.strftime("%Y-%m")

        # 단지 평단가
        complex_kb = (
            db.query(KBPriceModel)
            .filter(
                KBPriceModel.complex_id == target_complex.id,
                KBPriceModel.area_id == target_area.id,
                KBPriceModel.as_of_date.between(month_start, month_end),
                KBPriceModel.general_price.isnot(None),
            )
            .order_by(KBPriceModel.as_of_date.desc())
            .first()
        )

        complex_ppp = 0
        if complex_kb and complex_kb.general_price:
            complex_ppp = int(complex_kb.general_price / pyeong / 10000)

        # 읍면동 평균 평단가
        dong_ppp = _calc_regional_ppp(
            db, target_complex.region_code, month_start, month_end, level="dong"
        )

        # 시군구 평균 평단가
        sigungu_ppp = _calc_regional_ppp(
            db, target_complex.region_code, month_start, month_end, level="sigungu"
        )

        data_points.append(
            PricePerPyeongPoint(
                date=month_str,
                complex=complex_ppp,
                dong=dong_ppp or complex_ppp,
                sigungu=sigungu_ppp or complex_ppp,
            )
        )

    # 전체 데이터가 0이면 의미 없음
    if all(p.complex == 0 for p in data_points):
        return None

    address_parts = (target_complex.address or "").split()
    dong_name = address_parts[2] if len(address_parts) > 2 else "동"
    sigungu_name = address_parts[1] if len(address_parts) > 1 else "구"

    return PricePerPyeongTrend(
        complex_name=target_complex.name,
        dong_name=dong_name,
        sigungu_name=sigungu_name,
        data=data_points,
    )


def _calc_regional_ppp(
    db: Session,
    region_code: Optional[str],
    month_start: date,
    month_end: date,
    level: str = "dong",
) -> int:
    """지역 수준별(dong/sigungu) 평균 평단가를 계산한다."""
    if not region_code:
        return 0

    prefix = region_code if level == "dong" else region_code[:5]

    avg_price = (
        db.query(func.avg(KBPriceModel.general_price))
        .join(Complex, KBPriceModel.complex_id == Complex.id)
        .join(Area, KBPriceModel.area_id == Area.id)
        .filter(
            Complex.region_code.like(f"{prefix}%"),
            KBPriceModel.as_of_date.between(month_start, month_end),
            KBPriceModel.general_price.isnot(None),
            Area.pyeong.isnot(None),
            Area.pyeong > 0,
        )
        .scalar()
    )

    avg_pyeong = (
        db.query(func.avg(Area.pyeong))
        .join(KBPriceModel, Area.id == KBPriceModel.area_id)
        .join(Complex, KBPriceModel.complex_id == Complex.id)
        .filter(
            Complex.region_code.like(f"{prefix}%"),
            KBPriceModel.as_of_date.between(month_start, month_end),
            KBPriceModel.general_price.isnot(None),
            Area.pyeong.isnot(None),
            Area.pyeong > 0,
        )
        .scalar()
    )

    if avg_price and avg_pyeong and avg_pyeong > 0:
        return int(float(avg_price) / float(avg_pyeong) / 10000)

    return 0


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
