"""JB 적정시세 1단계 산출 — 동적 가중치 + 시간 감쇠 + IQR 이상치 제거.

참고: JB_적정시세_방법론.html

산출 흐름:
1. 실거래 IQR 이상치 제거 (Q1 - 1.5*IQR ~ Q3 + 1.5*IQR 밖 제외)
2. 실거래 시간 감쇠 가중평균
3. 매물 수 기반 호가 신뢰도
4. KB / 실거래 / 호가 신뢰도를 정규화해 동적 가중치 산출
5. jb_fair_price = 가중평균
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional, Tuple

# ── 시간 감쇠 (실거래 신뢰도) ──────────────────
# 자료의 "현업 판단 필요" 슬라이드 5 — 기본값
TIME_DECAY_BUCKETS = [
    (90,  1.00),   # 0~3개월: 100%
    (180, 0.70),   # 3~6개월: 70%
    (365, 0.45),   # 6~12개월: 45%
]
TIME_DECAY_OVER_YEAR = 0.20  # 12개월 초과: 20%


def time_decay_factor(days_ago: int) -> float:
    if days_ago < 0:
        return 1.0
    for bound, factor in TIME_DECAY_BUCKETS:
        if days_ago <= bound:
            return factor
    return TIME_DECAY_OVER_YEAR


# ── 매물 수 기반 호가 신뢰도 ─────────────────
# 슬라이드 6 — 기본값 (대단지 가정)
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


# ── IQR 이상치 제거 ────────────────────────
def iqr_filter(prices: List[int], multiplier: float = 1.5) -> List[int]:
    """Q1-1.5*IQR ~ Q3+1.5*IQR 범위 밖 제거. 4건 미만은 그대로 반환."""
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
    # 50% 이상 제거됐으면 원본 반환 (안전장치)
    if len(filtered) < len(prices) * 0.5:
        return prices
    return filtered


# ── 메인 산출 ──────────────────────────────
@dataclass
class JBComputeInput:
    kb_estimated: int                                    # KB 추정가 (latest)
    transactions: List[tuple[date, int]]                 # [(contract_date, price), ...] 12M
    active_listing_prices: List[int]                     # 현재 active 매물 호가
    today: date


@dataclass
class JBComputeResult:
    jb_fair_price: int                # 최종 JB 적정시세 (원)
    weights: dict[str, float]         # 정규화된 가중치 {kb, molit, naver}
    sources: dict[str, int]           # 각 소스 대표값 {kb, molit, naver}
    confidence: dict[str, float]      # 각 소스 신뢰도 (정규화 전)
    notes: list[str]                  # 산출 근거 메모


def compute_jb_fair_price(inp: JBComputeInput) -> JBComputeResult:
    notes: list[str] = []

    # 1) 실거래 IQR 이상치 제거
    raw_prices = [p for _, p in inp.transactions]
    filtered_prices = iqr_filter(raw_prices)
    removed = len(raw_prices) - len(filtered_prices)
    if removed > 0:
        notes.append(f"실거래 이상치 {removed}건 제거 (IQR)")

    # 2) 실거래 시간 감쇠 가중평균
    if filtered_prices:
        kept_dates = [d for d, p in inp.transactions if p in filtered_prices]
        # zip 다시 — 정확히 매칭
        kept = []
        used_set = set()
        for i, (d, p) in enumerate(inp.transactions):
            if p in filtered_prices and i not in used_set:
                kept.append((d, p))
                used_set.add(i)
        # 시간 감쇠
        weights_t = []
        for d, p in kept:
            days_ago = (inp.today - d).days
            w = time_decay_factor(days_ago)
            weights_t.append((p, w))
        total_w = sum(w for _, w in weights_t)
        if total_w > 0:
            molit_value = int(sum(p * w for p, w in weights_t) / total_w)
            # 실거래 신뢰도 = 평균 시간감쇠 * 거래 건수 보정 (5건 이상이면 1.0)
            avg_decay = total_w / len(weights_t)
            count_factor = min(len(weights_t) / 5.0, 1.0)
            molit_conf = avg_decay * count_factor
        else:
            molit_value = 0
            molit_conf = 0.0
    else:
        molit_value = 0
        molit_conf = 0.0
    notes.append(f"실거래 평균(가중) {molit_value:,}원 / 신뢰도 {molit_conf:.2f}")

    # 3) 호가 — 평균 + 매물 수 신뢰도
    naver_value = 0
    if inp.active_listing_prices:
        # 호가도 IQR 적용
        listing_filtered = iqr_filter(inp.active_listing_prices)
        naver_value = int(sum(listing_filtered) / len(listing_filtered))
    naver_conf = listing_count_confidence(len(inp.active_listing_prices))
    notes.append(
        f"호가 평균 {naver_value:,}원 / 매물 {len(inp.active_listing_prices)}건 / 신뢰도 {naver_conf:.2f}"
    )

    # 4) KB 신뢰도 — 항상 1.0 (기준선)
    kb_conf = 1.0 if inp.kb_estimated > 0 else 0.0

    # 5) 동적 가중치 정규화
    confidence = {"kb": kb_conf, "molit": molit_conf, "naver": naver_conf}
    total_conf = sum(confidence.values())
    if total_conf <= 0:
        # 데이터 없음 — KB 만 사용
        weights = {"kb": 1.0, "molit": 0.0, "naver": 0.0}
        jb = inp.kb_estimated
    else:
        weights = {k: round(v / total_conf, 3) for k, v in confidence.items()}
        jb = round(
            inp.kb_estimated * weights["kb"]
            + molit_value * weights["molit"]
            + naver_value * weights["naver"]
        )

    return JBComputeResult(
        jb_fair_price=jb,
        weights=weights,
        sources={"kb": inp.kb_estimated, "molit": molit_value, "naver": naver_value},
        confidence=confidence,
        notes=notes,
    )


# ── 예측 (단순 트렌드 + 신뢰구간) ───────────────
@dataclass
class ForecastPoint:
    month: int          # 0=현재, 1=+1개월, ...
    predicted: int
    lower: int          # 90% 신뢰구간 하한
    upper: int          # 90% 신뢰구간 상한


# 90% 신뢰구간 z-score
Z_90 = 1.645
SIGMA_FLOOR = 0.10  # 거래 표본 부족 시 변동성 하한 (±10% 보수적)


def project_jb_forecast(
    current_jb: int,
    transactions: List[Tuple[date, int]],
    today: date,
    horizon_months: int = 12,
) -> List[ForecastPoint]:
    """현재 JB와 실거래 12M 추이로 미래 horizon_months 예측.

    중심선:  current_jb × (1 + monthly_rate)^m
    하/상한: 중심선 × (1 ± Z_90 × σ_relative × √m)   ← 시간 누적 변동성

    σ_relative: 거래 표준편차/평균. 표본 5건 미만이면 SIGMA_FLOOR(10%) 적용.
    monthly_rate: 가장 오래된 거래 → 가장 최근 거래 변화율 / 개월
    """
    if current_jb <= 0:
        return []

    # IQR 이상치 제거
    raw_prices = [p for _, p in transactions]
    filtered = iqr_filter(raw_prices)
    used = [(d, p) for d, p in transactions if p in filtered]
    used.sort(key=lambda x: x[0])

    # 1) 월 변화율 (첫 ↔ 마지막)
    monthly_rate = 0.0
    if len(used) >= 2:
        first_date, first_price = used[0]
        last_date, last_price = used[-1]
        days = (last_date - first_date).days
        if days > 0 and first_price > 0:
            months = max(days / 30.4375, 1.0)
            ratio = last_price / first_price
            monthly_rate = math.log(ratio) / months  # 로그수익률 → 월 평균

    # 2) 변동성 σ_relative
    if len(filtered) >= 3:
        mean = statistics.mean(filtered)
        stdev = statistics.pstdev(filtered)
        sigma_rel = stdev / mean if mean > 0 else SIGMA_FLOOR
    else:
        sigma_rel = SIGMA_FLOOR
    sigma_rel = max(sigma_rel, SIGMA_FLOOR / 2)  # 너무 낮은 σ 방지

    # 3) 미래 산출
    # 신뢰구간 폭: 0개월에서 σ·Z (단기 변동성), 12개월에서 2σ·Z 까지 선형 증가
    # √m 보다 약하게 — 부동산은 평균회귀 경향 있어 무한 발산 X
    out: List[ForecastPoint] = []
    for m in range(0, horizon_months + 1):
        center = current_jb * math.exp(monthly_rate * m)
        if m == 0:
            spread = 0.0
            center = float(current_jb)
        else:
            time_factor = 1.0 + (m / 12.0)  # 0개월=1, 12개월=2
            spread = center * Z_90 * sigma_rel * time_factor
        out.append(ForecastPoint(
            month=m,
            predicted=int(round(center)),
            lower=int(round(max(center - spread, 0))),
            upper=int(round(center + spread)),
        ))
    return out
