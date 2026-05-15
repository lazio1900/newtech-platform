"""JB 적정시세 — 월별 대표값 × 고정 가중치 + OLS 예측.

산출 흐름:
1. 월별 집계: KB / 실거래 / 호가의 그 달 대표값
   - KB: 그 달 KB 스냅샷의 general_price 산술 평균
   - 실거래: 그 달 거래가의 IQR(1.5×) 이상치 제거 후 평균
   - 호가: 그 달에 살아있던 매물의 ask_price IQR(1.5×) 이상치 제거 후 평균
2. 시점별 JB: 사람이 정한 고정 가중치로 가중평균.
   - W_KB=0.4 / W_MOLIT=0.6 / W_NAVER=0.0 (호가는 수집 정상화 후 활성)
   - 그 달 실거래 결측이면 KB 단독 폴백
3. 예측: JB history 시계열을 로그-선형 OLS 회귀,
   잔차 표준편차로 80% 예측구간.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple


# ── 공통 도구 ───────────────────────────────
def iqr_filter(prices: List[int], multiplier: float = 1.5) -> List[int]:
    """Q1 - 1.5·IQR ~ Q3 + 1.5·IQR 밖 제거. 4건 미만은 그대로."""
    if len(prices) < 4:
        return prices
    sorted_prices = sorted(prices)
    n = len(sorted_prices)
    q1 = sorted_prices[n // 4]
    q3 = sorted_prices[(3 * n) // 4]
    iqr = q3 - q1
    if iqr == 0:
        return prices
    lo = q1 - multiplier * iqr
    hi = q3 + multiplier * iqr
    filtered = [p for p in prices if lo <= p <= hi]
    if len(filtered) < len(prices) * 0.5:
        return prices
    return filtered


def listing_count_confidence(active_count: int) -> float:
    """매물 수 → 호가 신뢰도 (0~1)."""
    if active_count >= 20:
        return 1.0
    if active_count >= 10:
        return 0.7
    if active_count >= 5:
        return 0.4
    if active_count >= 1:
        return 0.15
    return 0.0


def transaction_count_confidence(count: int) -> float:
    """월 거래 건수 → 실거래 신뢰도. 5건 이상이면 1.0."""
    if count <= 0:
        return 0.0
    return min(count / 5.0, 1.0)


# ── 월별 집계 ──────────────────────────────
@dataclass
class MonthlyAggregate:
    year: int
    month: int
    kb: Optional[int] = None
    kb_sample_count: int = 0
    molit: Optional[int] = None        # IQR 후 평균
    molit_sample_count: int = 0        # IQR 후 건수
    naver: Optional[int] = None        # IQR 후 평균
    naver_sample_count: int = 0        # 그 월에 살아있던 매물 수 (IQR 후)


def _month_iter(start: date, end: date) -> List[Tuple[int, int]]:
    y, m = start.year, start.month
    out: List[Tuple[int, int]] = []
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _month_bounds(year: int, month: int) -> Tuple[date, date]:
    """월의 [첫날, 다음달 첫날) 반열린 구간."""
    first = date(year, month, 1)
    if month == 12:
        next_first = date(year + 1, 1, 1)
    else:
        next_first = date(year, month + 1, 1)
    return first, next_first


def aggregate_monthly_series(
    kb_points: List[Tuple[date, int]],
    transactions: List[Tuple[date, int]],
    listings: List[Tuple[date, Optional[date], int]],
    start: date,
    end: date,
    listings_cold_start_months: int = 12,
) -> List[MonthlyAggregate]:
    """start~end 사이의 (year, month) 격자로 월별 집계.

    kb_points: [(as_of_date, general_price)]
    transactions: [(contract_date, price)]
    listings: [(posted_at_date, status_updated_at_date or None, ask_price)]
        호가의 "월 t 에 살아있던" 정의:
          posted_at < 다음달 1일 AND (status_updated_at is None OR status_updated_at >= 월초)
        (status_updated_at=None 은 여전히 ACTIVE 라는 의미로 취급)

    listings_cold_start_months:
        그 단지의 *최초* posted_at 으로부터 N 개월(캘린더 기준) 미만인 월은
        호가 표본을 사용하지 않는다 (강제 None). cold-start 단지에서 KB·실거래만으로
        JB 산출되도록.
    """
    keys = _month_iter(start, end)
    by_ym: dict[Tuple[int, int], MonthlyAggregate] = {
        k: MonthlyAggregate(year=k[0], month=k[1]) for k in keys
    }

    # KB — 산술 평균
    kb_bucket: dict[Tuple[int, int], List[int]] = {}
    for d, p in kb_points:
        if not p or p <= 0:
            continue
        k = (d.year, d.month)
        if k not in by_ym:
            continue
        kb_bucket.setdefault(k, []).append(p)
    for k, vals in kb_bucket.items():
        a = by_ym[k]
        a.kb = int(round(sum(vals) / len(vals)))
        a.kb_sample_count = len(vals)

    # 실거래 — IQR 후 평균
    txn_bucket: dict[Tuple[int, int], List[int]] = {}
    for d, p in transactions:
        if not p or p <= 0:
            continue
        k = (d.year, d.month)
        if k not in by_ym:
            continue
        txn_bucket.setdefault(k, []).append(p)
    for k, vals in txn_bucket.items():
        filtered = iqr_filter(vals)
        a = by_ym[k]
        a.molit = int(round(sum(filtered) / len(filtered)))
        a.molit_sample_count = len(filtered)

    # 호가 cold-start — 단지의 최초 posted_at 으로부터 12개월(캘린더) 미만인 월은 표본 사용 X
    valid_postings = [p for p, _, _ in listings if p is not None]
    listings_first = min(valid_postings) if valid_postings else None

    # 호가 — 살아있던 매물 IQR 후 평균
    for k in keys:
        if listings_first is None:
            continue
        months_since_first = (k[0] - listings_first.year) * 12 + (k[1] - listings_first.month)
        if months_since_first < listings_cold_start_months:
            continue
        first, next_first = _month_bounds(*k)
        alive: List[int] = []
        for posted, status_updated, price in listings:
            if not price or price <= 0 or posted is None:
                continue
            if posted >= next_first:
                continue
            if status_updated is not None and status_updated < first:
                continue
            alive.append(price)
        if not alive:
            continue
        filtered = iqr_filter(alive)
        a = by_ym[k]
        a.naver = int(round(sum(filtered) / len(filtered)))
        a.naver_sample_count = len(filtered)

    return [by_ym[k] for k in keys]


# ── 시점별 JB 산출 ─────────────────────────
@dataclass
class JBPoint:
    year: int
    month: int
    jb_fair_price: Optional[int]
    weights: dict[str, float]
    sources: dict[str, Optional[int]]
    confidence: dict[str, float]
    sample_counts: dict[str, int]


# 사람-정의 고정 가중치. 호가는 수집 안정화 후 활성. 합 1.0 이어야 함.
W_KB = 0.4
W_MOLIT = 0.6
W_NAVER = 0.0


def compute_jb_for_month(agg: MonthlyAggregate) -> JBPoint:
    """한 월의 고정 가중평균 JB 산출.

    - KB 없으면 산출 X (jb_fair_price=None).
    - 실거래 결측이면 KB 단독 (weights kb=1.0).
    - 호가는 W_NAVER=0 이라 실질 무시 (cold-start 후에 활성화).
    """
    sources = {"kb": agg.kb, "molit": agg.molit, "naver": agg.naver}
    samples = {
        "kb": agg.kb_sample_count,
        "molit": agg.molit_sample_count,
        "naver": agg.naver_sample_count,
    }

    if not agg.kb:
        return JBPoint(
            year=agg.year, month=agg.month,
            jb_fair_price=None,
            weights={"kb": 0.0, "molit": 0.0, "naver": 0.0},
            sources=sources,
            confidence={"kb": 0.0, "molit": 0.0, "naver": 0.0},
            sample_counts=samples,
        )

    # 실거래 결측 → KB 단독 폴백
    if not agg.molit:
        return JBPoint(
            year=agg.year, month=agg.month,
            jb_fair_price=int(agg.kb),
            weights={"kb": 1.0, "molit": 0.0, "naver": 0.0},
            sources=sources,
            confidence={"kb": 1.0, "molit": 0.0, "naver": 0.0},
            sample_counts=samples,
        )

    # 정상: KB×W_KB + 실거래×W_MOLIT (호가는 W_NAVER=0 으로 자동 제외)
    jb = agg.kb * W_KB + agg.molit * W_MOLIT + (agg.naver or 0) * W_NAVER
    return JBPoint(
        year=agg.year, month=agg.month,
        jb_fair_price=int(round(jb)),
        weights={"kb": W_KB, "molit": W_MOLIT, "naver": W_NAVER},
        sources=sources,
        confidence={"kb": 1.0, "molit": 1.0 if agg.molit else 0.0, "naver": 1.0 if agg.naver else 0.0},
        sample_counts=samples,
    )


# ── 현 시점 JB (응답 모델 호환) ─────────────
@dataclass
class JBComputeResult:
    jb_fair_price: int
    weights: dict[str, float]
    sources: dict[str, int]
    confidence: dict[str, float]
    notes: list[str]


def compute_latest_jb(series: List[MonthlyAggregate]) -> Optional[JBComputeResult]:
    """가장 최근의 JB 산출 가능한 월을 기준으로 현 시점 JB 산출."""
    for agg in reversed(series):
        pt = compute_jb_for_month(agg)
        if pt.jb_fair_price is None:
            continue
        w = pt.weights
        notes = [
            f"수행달 {agg.year}-{agg.month:02d}",
            f"수행달 가중치: KB {w['kb']*100:.0f}% / 실거래 {w['molit']*100:.0f}% / 호가 {w['naver']*100:.0f}%",
        ]
        if agg.kb:
            notes.append(f"KB {agg.kb_sample_count}건 평균 {agg.kb:,}원")
        if agg.molit:
            notes.append(f"실거래 {agg.molit_sample_count}건 평균 {agg.molit:,}원 (IQR 후)")
        else:
            notes.append("실거래 결측 → KB 단독 폴백")
        if agg.naver:
            notes.append(f"호가 {agg.naver_sample_count}건 평균 {agg.naver:,}원 (IQR 후, 현재 W=0 미반영)")
        else:
            notes.append("호가 데이터 없음")
        return JBComputeResult(
            jb_fair_price=pt.jb_fair_price,
            weights=pt.weights,
            sources={k: (v or 0) for k, v in pt.sources.items()},
            confidence=pt.confidence,
            notes=notes,
        )
    return None


# ── 예측 (로그-선형 가중 OLS, 최근 데이터 우선) ──
Z_80 = 1.282
MIN_HISTORY_FOR_OLS = 6
# 시간 감쇠 계수: 한 달 멀어질수록 weight 가 DECAY 배. 0.85 = 1개월 전 0.85, 11개월 전 ≈ 0.17.
# 작을수록 최근 정체 구간을 더 강하게 반영 → 외삽이 덜 가팔라짐.
DECAY = 0.85


@dataclass
class ForecastPoint:
    month: int          # 0 = 현재(마지막 관측월), 1 = +1개월, ...
    predicted: int
    lower: int          # 80% 신뢰구간 하한
    upper: int


def project_jb_forecast(
    jb_history: List[Tuple[int, int, int]],
    horizon_months: int = 12,
) -> List[ForecastPoint]:
    """jb_history=[(year, month, jb), ...] (값 있는 월만) 로그-선형 *가중* OLS 회귀.

    가중치 w_i = DECAY^(N-1-i) — 가장 최근 점이 1, 그 전 점들은 지수 감쇠.
    모델: log(JB_t) = α + β·t + ε, 최소화 Σ w_i·(y_i - (α + β·t_i))².

    중심선: exp(α + β·t*)
    예측 σ: σ_resid_w × √(1 + 1/N + (t* - t̄_w)² / Σ w_i(t_i - t̄_w)²)
    80% CI: 중심선 × exp(±Z_80·σ_pred)

    history < MIN_HISTORY_FOR_OLS 또는 분산 0 이면 빈 리스트.
    """
    if len(jb_history) < MIN_HISTORY_FOR_OLS:
        return []

    n = len(jb_history)
    t_idx = list(range(n))
    y = [math.log(jb) for _, _, jb in jb_history if jb > 0]
    if len(y) != n:
        return []

    weights = [DECAY ** (n - 1 - i) for i in range(n)]
    w_sum = sum(weights)
    t_bar_w = sum(w * t for w, t in zip(weights, t_idx)) / w_sum
    y_bar_w = sum(w * yi for w, yi in zip(weights, y)) / w_sum
    s_tt_w = sum(w * (t - t_bar_w) ** 2 for w, t in zip(weights, t_idx))
    if s_tt_w == 0:
        return []
    s_ty_w = sum(w * (t - t_bar_w) * (yi - y_bar_w) for w, t, yi in zip(weights, t_idx, y))
    beta = s_ty_w / s_tt_w
    alpha = y_bar_w - beta * t_bar_w

    residuals = [yi - (alpha + beta * t) for t, yi in zip(t_idx, y)]
    # 가중 평균 잔차 분산. OLS σ̂² 의 단순 가중 변형 (effective dof 보정 생략, 단순 명확).
    weighted_ss = sum(w * r * r for w, r in zip(weights, residuals))
    sigma_resid = math.sqrt(weighted_ss / max(w_sum, 1e-9))

    last_jb = jb_history[-1][2]
    out: List[ForecastPoint] = [ForecastPoint(0, last_jb, last_jb, last_jb)]
    for m in range(1, horizon_months + 1):
        t_future = (n - 1) + m
        log_center = alpha + beta * t_future
        sigma_pred = sigma_resid * math.sqrt(1 + 1 / n + ((t_future - t_bar_w) ** 2) / s_tt_w)
        spread = Z_80 * sigma_pred
        center = math.exp(log_center)
        lower = math.exp(log_center - spread)
        upper = math.exp(log_center + spread)
        out.append(ForecastPoint(
            month=m,
            predicted=int(round(center)),
            lower=int(round(max(lower, 0))),
            upper=int(round(upper)),
        ))
    return out
