"""LLM 기반 시세 분석 텍스트 생성.

CreditData(KB/실거래/호가) + JB 적정시세 + forecast + 인근 유사물건 + LTV 를
prompt 로 만들어 OpenAI 호출. 결과는 loan_applications.ai_market_text 에 캐시.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from models.loan import LoanApplication
from models.response_models import CreditData, NearbyPropertyTrends

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """당신은 한국 부동산 담보 평가 전문가입니다.
제공된 시세 데이터를 토대로 시세 분석을 JSON 형식으로 작성합니다.

JSON 키와 작성 가이드:
- "kb_시세":  KB 추정가 / 상하한 / 시세 추세
- "실거래가": 최근 실거래 가격, 거래 건수, 거래 추세 (안정/상승/하락)
- "매매호가": 현재 active 매물 평균/최신 호가, 매물 수, 시장 분위기
- "jb_적정시세": JB 동적 가중치 산출(KB/실거래/호가 가중치, 신뢰도, 이상치 제거)와 그 의미
- "예측": 향후 3개월 예측값과 90% 신뢰구간 하한선이 LTV 심사에 미칠 영향
- "ltv_검토": 채권합계와 시세 기준 LTV (현재시세 / JB 기준), 안전성
- "인근_유사물건": 1km 반경 같은 평형 단지들의 가격대, 평균 변동률, 기준 단지 대비 위치
- "종합_의견": 시세 안정성·LTV 적정성 종합 평가

작성 규칙:
- 각 값은 2~3문장의 한국어 존대형(~합니다) 평문. 마크다운/번호 금지.
- 제공된 사실(가격, 건수, 비율)만 사용. 임의 수치 추가 금지.
- "인근 평균 ~%" 같이 prompt 에 있는 값만 인용."""


def _format_won(v: Optional[int]) -> str:
    if not v:
        return "-"
    eok = v / 100_000_000
    return f"{eok:.2f}억"


def _fallback_text(credit: CreditData, loan_amount: int) -> str:
    return (
        "[종합 의견] AI 시세 분석 일시 사용 불가. "
        f"KB 추정가 {_format_won(credit.kb_price.estimated)}, "
        f"JB 적정시세 {_format_won(credit.jb_fair_price)}, "
        f"신청금액 {loan_amount:,}원 기준 LTV 산정이 필요합니다."
    )


def build_prompt(
    credit: CreditData,
    nearby: Optional[NearbyPropertyTrends],
    loan_amount: int,
    total_prior: int,
    pyeong: Optional[int] = None,
) -> str:
    kp = credit.kb_price
    mt = credit.molit_transactions
    nl = credit.naver_listings
    jd = credit.jb_detail

    # JB 동적 가중치 / 예측
    jb_section = ""
    if jd:
        w = jd.weights
        jb_section = (
            f"- JB 적정시세: {_format_won(jd.fair_price)}\n"
            f"- 동적 가중치: KB {w.get('kb', 0)*100:.0f}% / 실거래 {w.get('molit', 0)*100:.0f}% / 호가 {w.get('naver', 0)*100:.0f}%\n"
            f"- 산출 근거: {' / '.join(jd.notes)}\n"
        )
        if jd.forecast and len(jd.forecast) >= 4:
            f3 = jd.forecast[3]  # +3개월
            jb_section += (
                f"- +3개월 예측: 중심 {_format_won(f3.predicted)} / 하한 {_format_won(f3.lower)} / 상한 {_format_won(f3.upper)} (90% CI)\n"
            )

    # LTV
    jb_basis = (jd.fair_price if jd else 0) or kp.low or kp.estimated
    ltv_current = (total_prior / kp.estimated * 100) if kp.estimated else 0
    ltv_jb = (total_prior / jb_basis * 100) if jb_basis else 0

    # 인근 유사물건
    nearby_section = ""
    if nearby and nearby.similar_properties:
        radius = nearby.radius_m or 0
        avg_chg = (nearby.avg_change_rate or 0) * 100
        nearby_section = (
            f"- 검색 반경: {radius}m 내 같은 평형 단지 {len(nearby.similar_properties)}건\n"
            f"- 인근 평균 3개월 변동률: {avg_chg:+.1f}%\n"
            "- 단지별 (단지명, 거리, 최근가, 기준 대비, 3개월 변동, 유사도):\n"
        )
        for s in nearby.similar_properties[:5]:
            nearby_section += (
                f"  * {s.name} / {s.distance_m or 0}m / "
                f"{_format_won(s.recent_price)} / "
                f"{(s.price_diff_pct or 0):+.1f}% / "
                f"{(s.price_change_rate or 0)*100:+.1f}% / "
                f"유사도 {(s.similarity or 0)*100:.0f}\n"
            )

    return f"""다음 시세 데이터를 토대로 시세 분석을 작성하세요.

[KB 시세]
- 추정가: {_format_won(kp.estimated)} (상한 {_format_won(kp.high)} / 하한 {_format_won(kp.low)})
- 추세: {kp.trend}
- 12개월 history: {len(kp.history)}건

[국토부 실거래가]
- 최근 거래가: {_format_won(mt.recent_price)} ({mt.transaction_date})
- 추세: {mt.trend}
- 12개월 거래 건수: {len(mt.history)}

[매매호가 (KB 매물 수집)]
- 최신 호가: {_format_won(nl.avg_asking)}
- 활성 매물 수: {nl.listing_count}건
- 추세: {nl.trend}

[JB 적정시세 (1단계 동적 가중치 + IQR + 시간감쇠)]
{jb_section}

[LTV 검토]
- 채권합계 (선순위 + 신청금액): {total_prior:,}원
- 현재 시세 LTV: {ltv_current:.1f}% (KB 추정가 기준)
- JB 적정시세 LTV: {ltv_jb:.1f}%
- 평형: {pyeong}평

[인근 유사물건]
{nearby_section}

위 사실만 사용해 다음 8개 키를 모두 포함한 JSON 객체로 응답하세요:
{{"kb_시세": "...", "실거래가": "...", "매매호가": "...", "jb_적정시세": "...", "예측": "...", "ltv_검토": "...", "인근_유사물건": "...", "종합_의견": "..."}}
"""


def generate_or_get_cached(
    db: Session,
    application_id: Optional[str],
    credit: CreditData,
    nearby: Optional[NearbyPropertyTrends],
    loan_amount: int,
    total_prior: int,
    pyeong: Optional[int] = None,
) -> str:
    app = None
    if application_id:
        app = db.query(LoanApplication).filter(LoanApplication.id == application_id).first()
        if app and app.ai_market_text:
            logger.info(f"[ai_market] cache hit for {application_id}")
            return app.ai_market_text

    if not credit:
        return _fallback_text(credit, loan_amount)

    prompt = build_prompt(credit, nearby, loan_amount, total_prior, pyeong)

    try:
        from services.llm_service import LLMClient
        client = LLMClient()
        result = client.complete(prompt, system=SYSTEM_PROMPT, json_mode=True)
        raw = (result.get("text") or "").strip()
        if not raw:
            return _fallback_text(credit, loan_amount)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"[ai_market] JSON parse failed: {e}")
            return _fallback_text(credit, loan_amount)

        def _flatten(val) -> str:
            """LLM 이 dict/list 로 응답해도 평문화."""
            if val is None:
                return ""
            if isinstance(val, str):
                return val.strip()
            if isinstance(val, list):
                return " ".join(_flatten(v) for v in val)
            if isinstance(val, dict):
                return " ".join(f"{k}: {_flatten(v)}" for k, v in val.items())
            return str(val).strip()

        sections = [
            ("[KB 시세]", parsed.get("kb_시세")),
            ("[실거래가]", parsed.get("실거래가")),
            ("[매매호가]", parsed.get("매매호가")),
            ("[JB 적정시세]", parsed.get("jb_적정시세")),
            ("[예측]", parsed.get("예측")),
            ("[LTV 검토]", parsed.get("ltv_검토")),
            ("[인근 유사물건]", parsed.get("인근_유사물건")),
            ("[종합 의견]", parsed.get("종합_의견")),
        ]
        parts = [f"{label}\n{_flatten(body)}" for label, body in sections if _flatten(body)]
        text = "\n\n".join(parts)
        if not text:
            return _fallback_text(credit, loan_amount)

        if app:
            app.ai_market_text = text
            app.ai_market_generated_at = datetime.utcnow()
            db.commit()
            logger.info(
                f"[ai_market] cached for {application_id} "
                f"(tokens: in={result.get('prompt_tokens')}, out={result.get('completion_tokens')})"
            )
        return text
    except Exception as e:
        logger.warning(f"[ai_market] LLM call failed: {e}")
        return _fallback_text(credit, loan_amount)
