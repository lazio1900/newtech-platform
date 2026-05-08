"""LLM 기반 입지 분석 텍스트 생성.

facility 데이터 + LocationScores + Complex 정보를 prompt 로 만들어
OpenAI ChatCompletion (JSON mode) 호출. 7개 항목을 받아 텍스트로 조합.
결과는 loan_applications.ai_analysis_text 에 캐시.

cache miss 시에만 호출. 실패 시 fallback 텍스트 반환.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime
from typing import Optional, List

from sqlalchemy.orm import Session

from models.complex import Complex
from models.facility import ComplexFacility
from models.loan import LoanApplication
from models.response_models import LocationScores

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """당신은 한국 부동산 담보 평가 전문가입니다.
주어진 단지 정보와 주변 시설 데이터를 바탕으로 입지 분석을 JSON 형식으로 작성합니다.

JSON 키와 각 항목 작성 가이드:
- "역세권": 가장 가까운 지하철역까지의 거리/도보분 (분=거리÷80m). 노선 종류는 다음 항목에서.
- "노선_다양성": 1km 박스 내 역 수와 호선 종류만. 거리 반복 X.
- "단지_규모": 세대수, 준공년도, 복도타입, 평형 등 단지 자체 특성.
- "학군": 가장 가까운 초등 + 어린이집/유치원/중/고 분포.
- "생활환경": 주변 의료시설(병원) 밀도와 가장 가까운 거리. 공원 언급 X.
- "자연환경": 공원/녹지 거리 + 1km 내 개수.
- "종합_의견": 위 6개 항목과 평균 점수 토대로 종합 평가.

작성 규칙:
- 각 값은 2~3문장의 한국어 존대형(~합니다) 평문. 마크다운/번호 금지.
- 제공된 사실(거리, 개수, 점수)만 사용. 임의 수치 추가 금지.
- 데이터에 없는 표현 추측 금지 (한강뷰, 학원가 등)."""


def _format_subway(subways: List[ComplexFacility]) -> str:
    if not subways:
        return "주변 1.3km 박스 내 지하철역 없음"
    near = min(subways, key=lambda f: f.distance_m or 99999)
    lines = sorted({f.sub_type for f in subways if f.sub_type})
    return (
        f"가장 가까운 역 {near.name}({near.distance_m}m), "
        f"노선: {', '.join(lines) if lines else '정보없음'}, "
        f"1km 박스 내 {len(subways)}개 역"
    )


def _format_schools(schools: List[ComplexFacility]) -> str:
    if not schools:
        return "주변 학교 없음"
    elem = [s for s in schools if s.sub_type == "elementary"]
    near_elem = min(elem, key=lambda f: f.distance_m or 99999) if elem else None
    counts = Counter(s.sub_type for s in schools)
    parts = []
    if near_elem:
        parts.append(f"가장 가까운 초등 {near_elem.name}({near_elem.distance_m}m)")
    parts.append(
        "분포: 어린이집 {kindergarten}, 유치원 {preschool}, 초 {elementary}, 중 {middle}, 고 {high}".format(
            kindergarten=counts.get("kindergarten", 0),
            preschool=counts.get("preschool", 0),
            elementary=counts.get("elementary", 0),
            middle=counts.get("middle", 0),
            high=counts.get("high", 0),
        )
    )
    return ". ".join(parts)


def _format_hospitals(hospitals: List[ComplexFacility]) -> str:
    if not hospitals:
        return "주변 1km 내 병원 정보 없음"
    near = min(hospitals, key=lambda f: f.distance_m or 99999)
    within_1km = [h for h in hospitals if (h.distance_m or 99999) <= 1000]
    return (
        f"가장 가까운 병원 {near.distance_m}m, 1km 내 {len(within_1km)}개"
    )


def _format_parks(parks: List[ComplexFacility]) -> str:
    if not parks:
        return "주변 1km 내 공원/녹지 없음"
    near = min(parks, key=lambda f: f.distance_m or 99999)
    return (
        f"가장 가까운 {near.name}({near.distance_m}m), 1km 내 공원/녹지 {len(parks)}곳"
    )


def build_prompt(
    complex_obj: Complex,
    facilities: List[ComplexFacility],
    scores: LocationScores,
    pyeong: Optional[int] = None,
) -> str:
    schools = [f for f in facilities if f.facility_type == "school"]
    subways = [f for f in facilities if f.facility_type == "subway"]
    hospitals = [f for f in facilities if f.facility_type == "hospital"]
    parks = [f for f in facilities if f.facility_type == "park"]

    avg_score = round(
        (scores.station_walk + scores.commute_time + scores.school_walk
         + scores.units_score + scores.living_env + scores.nature_env) / 6
    )

    return f"""다음 단지의 입지 분석을 작성하세요.

[단지 기본]
- 단지명: {complex_obj.name}
- 주소: {complex_obj.address or "-"}
- 세대수: {complex_obj.total_households or "정보없음"}세대
- 준공: {complex_obj.built_year or "-"}
- 복도타입: {complex_obj.hallway_type or "-"}
- 평형: {pyeong}평 (전용)

[교통]
{_format_subway(subways)}

[학군]
{_format_schools(schools)}

[생활환경 - 의료]
{_format_hospitals(hospitals)}

[자연환경]
{_format_parks(parks)}

[입지점수 — 0~100]
- 역세권(거리): {scores.station_walk}
- 통근편의(노선다양성 포함): {scores.commute_time}
- 초등학교(거리): {scores.school_walk}
- 세대수/규모: {scores.units_score}
- 생활환경(병원밀도): {scores.living_env}
- 자연환경(공원): {scores.nature_env}
- 평균: {avg_score}점

위 사실만 사용해 다음 7개 키를 모두 포함한 JSON 객체로 응답하세요. 키 이름은 정확히 그대로:
{{"역세권": "...", "노선_다양성": "...", "단지_규모": "...", "학군": "...", "생활환경": "...", "자연환경": "...", "종합_의견": "..."}}
"""


def _fallback_text(scores: LocationScores) -> str:
    avg = round(
        (scores.station_walk + scores.commute_time + scores.school_walk
         + scores.units_score + scores.living_env + scores.nature_env) / 6
    )
    return (
        f"[종합 의견] AI 자동 분석 일시 사용 불가. 산출된 입지 점수 평균 {avg}점을 참고하시기 바랍니다."
    )


def generate_or_get_cached(
    db: Session,
    application_id: Optional[str],
    complex_obj: Complex,
    scores: LocationScores,
    pyeong: Optional[int] = None,
) -> str:
    """LLM 입지 분석 — 캐시 우선, 없으면 OpenAI 호출.

    - application_id 가 주어지고 캐시 있으면 재사용
    - 없으면 호출 후 캐시 저장
    - LLM 실패 시 fallback 반환 (캐시 안 함 — 다음 호출에 재시도 여지)
    """
    app = None
    if application_id:
        app = db.query(LoanApplication).filter(LoanApplication.id == application_id).first()
        if app and app.ai_analysis_text:
            logger.info(f"[ai_analysis] cache hit for application {application_id}")
            return app.ai_analysis_text

    facilities = (
        db.query(ComplexFacility)
        .filter(ComplexFacility.complex_id == complex_obj.id)
        .all()
    )
    if not facilities:
        # facility 없으면 LLM 호출 의미 없음 — 안내 메시지
        return _fallback_text(scores)

    prompt = build_prompt(complex_obj, facilities, scores, pyeong=pyeong)

    try:
        from services.llm_service import LLMClient

        client = LLMClient()
        result = client.complete(prompt, system=SYSTEM_PROMPT, json_mode=True)
        raw = (result.get("text") or "").strip()
        if not raw:
            return _fallback_text(scores)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"[ai_analysis] JSON parse failed: {e}; raw[:200]={raw[:200]}")
            return _fallback_text(scores)

        # 7개 라벨 순서대로 평면 텍스트 조합
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

        sections = [
            ("[역세권]", parsed.get("역세권")),
            ("[노선 다양성]", parsed.get("노선_다양성")),
            ("[단지 규모]", parsed.get("단지_규모")),
            ("[학군]", parsed.get("학군")),
            ("[생활환경]", parsed.get("생활환경")),
            ("[자연환경]", parsed.get("자연환경")),
            ("[종합 의견]", parsed.get("종합_의견")),
        ]
        parts = [f"{label}\n{_flatten(body)}" for label, body in sections if _flatten(body)]
        text = "\n\n".join(parts)
        if not text:
            return _fallback_text(scores)

        if app:
            app.ai_analysis_text = text
            app.ai_analysis_generated_at = datetime.utcnow()
            db.commit()
            logger.info(
                f"[ai_analysis] generated and cached for application {application_id} "
                f"(tokens: in={result.get('prompt_tokens')}, out={result.get('completion_tokens')})"
            )
        return text
    except Exception as e:
        logger.warning(f"[ai_analysis] LLM call failed: {e}")
        return _fallback_text(scores)
