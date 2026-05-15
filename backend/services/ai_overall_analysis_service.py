"""LLM 기반 AI 종합 의견 + 심사역 권고.

모든 사실 기반 데이터(입지점수/시세/JB/예측/유사/평단가/등기부/LTV)를 종합해
JSON 두 가지 출력:
  - comprehensive_opinion: 6개 항목 [입지][권리][시세][유사물건][평단가][LTV] 자연어
  - auditor_recommendation: 심사역 권고 의견 초안 (3~5문장)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from models.loan import LoanApplication
from models.response_models import (
    AnalysisData, CreditData, NearbyPropertyTrends, PricePerPyeongTrend,
    PropertyBasicInfo, PropertyRightsInfo, LocationScores,
)

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """당신은 한국 부동산 담보 대출 심사 전문가입니다.
주어진 분석 데이터(사실)를 토대로 JSON 으로 응답합니다.

JSON 키:
- "comprehensive_opinion": 항목별 한 줄씩 작성. 라벨은 정확히 [입지] [권리] [시세] [유사물건] [평단가] [LTV].
    각 라벨 뒤에 한 줄(1~2문장)씩, 줄바꿈으로 구분.
- "auditor_recommendation": 심사역 권고 의견 초안. 3~5문장의 한 단락.
    LTV·권리상태·시세 안정성·예측 신뢰구간 하한 등을 종합해 대출 실행 가부 / 조건부 / 한도조정 / 보류 관점에서 제안.
    심사역이 그대로 사용 가능한 자연스러운 어조 (~합니다, ~판단됩니다).

작성 규칙:
- 제공된 사실(점수, 거리, 비율, 금액)만 사용. 추측·임의 수치 금지.
- "comprehensive_opinion" 은 6개 라벨 모두 반드시 포함.
- 마크다운 / 번호매김 금지. 평문."""


def _won(v: Optional[int]) -> str:
    if not v:
        return "-"
    return f"{v / 100_000_000:.2f}억"


def _flatten(val) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, list):
        return "\n".join(_flatten(v) for v in val)
    if isinstance(val, dict):
        return "\n".join(f"{k}: {_flatten(v)}" for k, v in val.items())
    return str(val).strip()


def build_prompt(
    pbi: PropertyBasicInfo,
    scores: Optional[LocationScores],
    credit: CreditData,
    nearby: Optional[NearbyPropertyTrends],
    ppp: Optional[PricePerPyeongTrend],
    rights: PropertyRightsInfo,
    loan_amount: int,
    ltv_current: float,
    ltv_jb: float,
) -> str:
    # 입지점수
    sc_section = "데이터 없음"
    if scores:
        avg = round((scores.station_walk + scores.commute_time + scores.school_walk
                     + scores.units_score + scores.living_env + scores.nature_env) / 6)
        sc_section = (
            f"역세권 {scores.station_walk} / 노선 {scores.commute_time} / "
            f"학군 {scores.school_walk} / 단지규모 {scores.units_score} / "
            f"생활 {scores.living_env} / 자연 {scores.nature_env}  (평균 {avg})"
        )

    # JB / 예측
    jb_section = ""
    jd = credit.jb_detail
    if jd:
        w = jd.weights
        jb_section = (
            f"  JB 적정시세: {_won(jd.fair_price)} "
            f"(KB {w.get('kb',0)*100:.0f}% / 실거래 {w.get('molit',0)*100:.0f}% / 호가 {w.get('naver',0)*100:.0f}%)\n"
        )
        if jd.forecast and len(jd.forecast) >= 4:
            f3 = jd.forecast[3]
            jb_section += (
                f"  +3개월 예측: 중심 {_won(f3.predicted)} / 하한 {_won(f3.lower)} / 상한 {_won(f3.upper)} (80% CI)\n"
            )

    # 인근 유사물건
    nb_section = "데이터 없음"
    if nearby and nearby.similar_properties:
        nb_section = (
            f"반경 {nearby.radius_m or 0}m / 같은 평형 {len(nearby.similar_properties)}건 / "
            f"평균 변동 {(nearby.avg_change_rate or 0)*100:+.1f}% / "
            f"기준가 {_won(nearby.target_recent_price)}"
        )

    # 평단가
    ppp_section = "데이터 없음"
    if ppp and ppp.data:
        latest = ppp.data[-1]
        if latest.complex and latest.dong:
            ppp_section = (
                f"단지 {latest.complex:,}원/평 vs 동 평균 {latest.dong:,}원/평 "
                f"({(latest.complex-latest.dong)/latest.dong*100:+.1f}%) "
                f"vs 시군구 평균 {latest.sigungu:,}원/평"
            )

    # 권리
    rights_section = (
        f"근저당 {len(rights.mortgage_entries)}건, "
        f"기타등기 {len(rights.ownership_other_entries)}건, "
        f"채권최고액 {_won(rights.max_bond_amount)}, "
        f"임차보증금 {_won(rights.tenant_deposit) if rights.tenant_deposit else '없음'}"
    )

    return f"""다음 분석 데이터를 토대로 종합 의견 JSON 을 작성하세요.

[담보 단지]
- 단지명: {pbi.complex_name}
- 주소: {pbi.address}
- 세대수: {pbi.units}세대 / 연식: {pbi.age}년
- 전용면적: {pbi.exclusive_m2}㎡ / 평형: {pbi.area}평

[입지점수]
{sc_section}

[권리]
{rights_section}

[시세]
- KB 추정가: {_won(credit.kb_price.estimated)} (상한 {_won(credit.kb_price.high)} / 하한 {_won(credit.kb_price.low)})
- 실거래 최근가: {_won(credit.molit_transactions.recent_price)} ({credit.molit_transactions.transaction_date})
- 호가 최신: {_won(credit.naver_listings.avg_asking)} (매물 {credit.naver_listings.listing_count}건)
{jb_section}

[유사물건]
{nb_section}

[평단가]
{ppp_section}

[LTV]
- 채권합계: {_won(rights.max_bond_amount + rights.tenant_deposit + loan_amount)}
- 현재 시세 LTV: {ltv_current:.1f}% (KB 추정가 기준)
- JB 적정시세 LTV: {ltv_jb:.1f}%

위 데이터로 시스템 메시지에 명시된 JSON 을 응답하세요.
"""


def generate_or_get_cached(
    db: Session,
    application_id: Optional[str],
    pbi: PropertyBasicInfo,
    scores: Optional[LocationScores],
    credit: CreditData,
    nearby: Optional[NearbyPropertyTrends],
    ppp: Optional[PricePerPyeongTrend],
    rights: PropertyRightsInfo,
    loan_amount: int,
    ltv_current: float,
    ltv_jb: float,
) -> dict:
    """반환: {"comprehensive_opinion": str, "auditor_recommendation": str}."""
    fallback = {
        "comprehensive_opinion": "",
        "auditor_recommendation": "",
    }

    app = None
    if application_id:
        app = db.query(LoanApplication).filter(LoanApplication.id == application_id).first()
        if app and app.ai_overall_text:
            try:
                return json.loads(app.ai_overall_text)
            except json.JSONDecodeError:
                pass

    prompt = build_prompt(
        pbi, scores, credit, nearby, ppp, rights, loan_amount, ltv_current, ltv_jb,
    )

    try:
        from services.llm_service import LLMClient
        from services.prompt_registry import get_prompt
        client = LLMClient()
        system_prompt = get_prompt(db, "overall", "system", SYSTEM_PROMPT)
        result = client.complete(prompt, system=system_prompt, json_mode=True)
        raw = (result.get("text") or "").strip()
        if not raw:
            return fallback
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"[ai_overall] JSON parse failed: {e}")
            return fallback

        out = {
            "comprehensive_opinion": _flatten(parsed.get("comprehensive_opinion")),
            "auditor_recommendation": _flatten(parsed.get("auditor_recommendation")),
        }
        if not out["comprehensive_opinion"] and not out["auditor_recommendation"]:
            return fallback

        if app:
            app.ai_overall_text = json.dumps(out, ensure_ascii=False)
            app.ai_overall_generated_at = datetime.utcnow()
            db.commit()
            logger.info(
                f"[ai_overall] cached for {application_id} "
                f"(in={result.get('prompt_tokens')}, out={result.get('completion_tokens')})"
            )
        return out
    except Exception as e:
        logger.warning(f"[ai_overall] LLM call failed: {e}")
        return fallback
