"""LLM 기반 유사물건 종합 코멘트.

인근 유사물건 + 평단가 추이(단지/읍면동/시군구) → 종합 평가.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from models.loan import LoanApplication
from models.response_models import NearbyPropertyTrends, PricePerPyeongTrend

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """당신은 한국 부동산 담보 평가 전문가입니다.
인근 유사 단지 분석과 평단가 추이를 토대로 종합 코멘트를 JSON 으로 작성합니다.

JSON 키:
- "위치_평가":  타겟 단지가 인근 같은 평형 단지들 사이에서 가격대(저/평균/고)와 거리상 위치
- "평단가_평가": 단지/읍면동/시군구 평단가 비교 (단지가 동/시군구 평균 대비 어디인지)
- "시장_분위기": 인근 평균 변동률 + 단지별 +-% 분포로 시장 상승/하락/혼조 판단
- "종합_의견":  위 3개를 토대로 담보가치 측면에서의 시사점 (1~2문장)

작성 규칙:
- 각 값은 2~3문장의 한국어 존대형(~합니다) 평문. 마크다운/번호 금지.
- 제공된 사실(가격, 변동률)만 사용. 추측 금지."""


def _format_won(v: Optional[int]) -> str:
    if not v:
        return "-"
    return f"{v / 100_000_000:.2f}억"


def _flatten(val) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, list):
        return " ".join(_flatten(v) for v in val)
    if isinstance(val, dict):
        return " ".join(f"{k}: {_flatten(v)}" for k, v in val.items())
    return str(val).strip()


def build_prompt(
    target_complex_name: str,
    target_recent_price: Optional[int],
    nearby: NearbyPropertyTrends,
    ppp: Optional[PricePerPyeongTrend],
) -> str:
    nearby_lines = []
    for s in nearby.similar_properties[:5]:
        nearby_lines.append(
            f"  * {s.name} / 거리 {s.distance_m}m / {s.area}평 / {s.units}세대 / {s.age}년 / "
            f"최근가 {_format_won(s.recent_price)} / 기준대비 {(s.price_diff_pct or 0):+.1f}% / "
            f"3M변동 {(s.price_change_rate or 0)*100:+.1f}% / 유사도 {(s.similarity or 0)*100:.0f}"
        )

    ppp_section = ""
    if ppp and ppp.data:
        latest = ppp.data[-1]
        ppp_section = (
            f"- 단지 평단가:    {latest.complex:,}원/평\n"
            f"- 읍면동 평단가:  {latest.dong:,}원/평\n"
            f"- 시군구 평단가:  {latest.sigungu:,}원/평\n"
            f"- 단지 vs 동: {(latest.complex - latest.dong) / latest.dong * 100:+.1f}%\n"
            f"- 단지 vs 시군구: {(latest.complex - latest.sigungu) / latest.sigungu * 100:+.1f}%\n"
        )
    else:
        ppp_section = "- 평단가 데이터 부족\n"

    return f"""다음 데이터를 토대로 유사물건 종합 코멘트를 작성하세요.

[타겟 단지]
- 단지명: {target_complex_name}
- 최근 거래가: {_format_won(target_recent_price)}

[인근 유사 단지 — {len(nearby.similar_properties)}건]
- 검색 반경: {nearby.radius_m or 0}m
- 인근 평균 3개월 변동률: {(nearby.avg_change_rate or 0)*100:+.1f}%
{chr(10).join(nearby_lines)}

[평단가 추이 (가장 최근 시점)]
{ppp_section}

위 사실만 사용해 다음 4개 키 JSON 으로 응답하세요:
{{"위치_평가": "...", "평단가_평가": "...", "시장_분위기": "...", "종합_의견": "..."}}
"""


def generate_or_get_cached(
    db: Session,
    application_id: Optional[str],
    target_complex_name: str,
    target_recent_price: Optional[int],
    nearby: Optional[NearbyPropertyTrends],
    ppp: Optional[PricePerPyeongTrend],
) -> str:
    if not nearby or not nearby.similar_properties:
        return "[종합 의견] 인근 유사 단지 데이터가 부족하여 종합 분석을 작성할 수 없습니다."

    app = None
    if application_id:
        app = db.query(LoanApplication).filter(LoanApplication.id == application_id).first()
        if app and app.ai_nearby_text:
            logger.info(f"[ai_nearby] cache hit for {application_id}")
            return app.ai_nearby_text

    prompt = build_prompt(target_complex_name, target_recent_price, nearby, ppp)

    try:
        from services.llm_service import LLMClient
        client = LLMClient()
        result = client.complete(prompt, system=SYSTEM_PROMPT, json_mode=True)
        raw = (result.get("text") or "").strip()
        if not raw:
            return "[종합 의견] AI 분석 결과가 비어있습니다."
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"[ai_nearby] JSON parse failed: {e}")
            return "[종합 의견] AI 분석 응답 파싱 실패."

        sections = [
            ("[위치 평가]", parsed.get("위치_평가")),
            ("[평단가 평가]", parsed.get("평단가_평가")),
            ("[시장 분위기]", parsed.get("시장_분위기")),
            ("[종합 의견]", parsed.get("종합_의견")),
        ]
        parts = [f"{label}\n{_flatten(body)}" for label, body in sections if _flatten(body)]
        text = "\n\n".join(parts)
        if not text:
            return "[종합 의견] AI 분석 결과가 비어있습니다."

        if app:
            app.ai_nearby_text = text
            app.ai_nearby_generated_at = datetime.utcnow()
            db.commit()
            logger.info(
                f"[ai_nearby] cached for {application_id} "
                f"(in={result.get('prompt_tokens')}, out={result.get('completion_tokens')})"
            )
        return text
    except Exception as e:
        logger.warning(f"[ai_nearby] LLM call failed: {e}")
        return "[종합 의견] AI 분석 일시 사용 불가."
