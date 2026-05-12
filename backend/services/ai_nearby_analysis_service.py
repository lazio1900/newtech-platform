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
- "평단가_평가": 단지/읍면동/시군구 평단가 비교. **격차가 크면 단순 "유사" 라 표현하지 말고 그 의미(입지·연식·평형·세대 등급 차이) 를 짚어줄 것.**
- "시장_분위기": 인근 평균 변동률 + 단지별 +-% 분포로 시장 상승/하락/혼조 판단
- "종합_의견":  위 3개를 토대로 담보가치 측면에서의 시사점 (1~2문장)

**평단가 비교 도메인 판단 기준** (부동산 전문가 관점):
- 차이 ±5% 이내 → "동/구 평균과 유사" 표현 가능
- 차이 ±5~15% → "약간의 편차" / "다소 높은(낮은) 편"
- 차이 ±15% 초과 → "유사" 사용 금지. **"상당한 격차"** 로 표현하고 원인(역세권/학군/연식/대단지 프리미엄 등) 가능성 1줄 명시
- 절대값으로 1,000만원/평 이상 차이는 시장상 큰 편차로 간주 (서울 평균 시장 5천~6천만원/평 기준 약 20%)
- **동 평단가와 구 평단가가 2,000만원/평 이상 차이나는데 "유사" 라고 쓰면 도메인 오류임**

**부동산 도메인 인과 추론 규칙** (중요):
- 일반적으로 **연식이 짧을수록(신축) 가격 ↑**, **세대수가 클수록 가격 ↑**, **역세권/학군 좋을수록 ↑**.
  반대 인과를 가격 하락의 이유로 들지 말 것 (예: "연식이 짧아서 저렴" 은 도메인 오류).
- **타겟 단지의 속성(연식·세대수·평형) 은 [타겟 단지] 섹션에 명시된 값만 인용.** 명시 안 됐으면 그 속성을 추측해 이유로 들지 말 것.
- 인근 단지 평균과 비교할 때 실제 수치 차이를 근거로만 추론. "A이기 때문에 B" 같은 단정적 인과는 데이터 근거 있을 때만.
- 원인을 모를 때는 "가격 차이의 원인은 입지·학군 등 추가 확인이 필요합니다" 처럼 보류 표현.

작성 규칙:
- 각 값은 2~3문장의 한국어 존대형(~합니다) 평문. 마크다운/번호 금지.
- 평단가는 반드시 **"만원/평" 단위**로 표기 (예: "6,534만원/평"). **"원/평" 사용 금지** — 입력 데이터 단위가 만원임.
- 제공된 사실(가격, 변동률, 연식, 세대수, 평형)만 사용. 추측 금지."""


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
    target_pyeong: Optional[int] = None,
    target_age: Optional[int] = None,
    target_units: Optional[int] = None,
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
        c_vs_d_pct = (latest.complex - latest.dong) / latest.dong * 100 if latest.dong else 0
        c_vs_s_pct = (latest.complex - latest.sigungu) / latest.sigungu * 100 if latest.sigungu else 0
        d_vs_s_pct = (latest.dong - latest.sigungu) / latest.sigungu * 100 if latest.sigungu else 0
        ppp_section = (
            f"- 단지 평단가:    {latest.complex:,}만원/평\n"
            f"- 읍면동 평단가:  {latest.dong:,}만원/평\n"
            f"- 시군구 평단가:  {latest.sigungu:,}만원/평\n"
            f"- 단지 vs 동:     {latest.complex - latest.dong:+,}만원/평 ({c_vs_d_pct:+.1f}%)\n"
            f"- 단지 vs 시군구: {latest.complex - latest.sigungu:+,}만원/평 ({c_vs_s_pct:+.1f}%)\n"
            f"- 동 vs 시군구:   {latest.dong - latest.sigungu:+,}만원/평 ({d_vs_s_pct:+.1f}%)\n"
        )
    else:
        ppp_section = "- 평단가 데이터 부족\n"

    target_lines = [
        f"- 단지명: {target_complex_name}",
        f"- 최근 거래가: {_format_won(target_recent_price)}",
    ]
    if target_pyeong is not None:
        target_lines.append(f"- 평형: {target_pyeong}평")
    if target_age is not None:
        target_lines.append(f"- 연식: {target_age}년차")
    if target_units is not None:
        target_lines.append(f"- 세대수: {target_units}세대")

    return f"""다음 데이터를 토대로 유사물건 종합 코멘트를 작성하세요.

[타겟 단지]
{chr(10).join(target_lines)}

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
    target_pyeong: Optional[int] = None,
    target_age: Optional[int] = None,
    target_units: Optional[int] = None,
) -> str:
    if not nearby or not nearby.similar_properties:
        return "[종합 의견] 인근 유사 단지 데이터가 부족하여 종합 분석을 작성할 수 없습니다."

    app = None
    if application_id:
        app = db.query(LoanApplication).filter(LoanApplication.id == application_id).first()
        if app and app.ai_nearby_text:
            logger.info(f"[ai_nearby] cache hit for {application_id}")
            return app.ai_nearby_text

    prompt = build_prompt(
        target_complex_name, target_recent_price, nearby, ppp,
        target_pyeong=target_pyeong, target_age=target_age, target_units=target_units,
    )

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
