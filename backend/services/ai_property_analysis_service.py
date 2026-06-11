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
from models.response_models import ComplexScores, LocationScores

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


def _flatten(val) -> str:
    """LLM JSON 값(문자열/리스트/딕셔너리)을 평문으로 조합."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, list):
        return " ".join(_flatten(v) for v in val)
    if isinstance(val, dict):
        return " ".join(f"{k}: {_flatten(v)}" for k, v in val.items())
    return str(val).strip()


def _assemble(parsed: dict, sections: list) -> str:
    """(label, key) 순서대로 파싱 결과를 평문 텍스트로 조합."""
    parts = [f"{label}\n{_flatten(parsed.get(key))}"
             for label, key in sections if _flatten(parsed.get(key))]
    return "\n\n".join(parts)


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
        from services.prompt_registry import get_prompt

        client = LLMClient()
        system_prompt = get_prompt(db, "property", "system", SYSTEM_PROMPT)
        result = client.complete(prompt, system=system_prompt, json_mode=True)
        raw = (result.get("text") or "").strip()
        if not raw:
            return _fallback_text(scores)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"[ai_analysis] JSON parse failed: {e}; raw[:200]={raw[:200]}")
            return _fallback_text(scores)

        # 7개 라벨 순서대로 평면 텍스트 조합
        text = _assemble(parsed, [
            ("[역세권]", "역세권"),
            ("[노선 다양성]", "노선_다양성"),
            ("[단지 규모]", "단지_규모"),
            ("[학군]", "학군"),
            ("[생활환경]", "생활환경"),
            ("[자연환경]", "자연환경"),
            ("[종합 의견]", "종합_의견"),
        ])
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


# ─────────────────────────────────────────────────────────────────────────────
# 내부망(CCTR_*) 모드 — 좌표/주변시설 없이 단지·시세 특성으로 분석
# ─────────────────────────────────────────────────────────────────────────────

COMPLEX_SYSTEM_PROMPT = """당신은 한국 부동산 담보 평가 전문가입니다.
폐쇄망 내부 데이터(단지 기본정보 + KB 시세)만으로 담보 물건의 단지 특성을 분석합니다.
주변 시설·좌표 데이터는 제공되지 않으므로 역세권·학군·교통·생활환경은 언급하지 않습니다.

JSON 키와 각 항목 작성 가이드:
- "단지_규모": 세대수와 동수로 본 규모·환금성.
- "연식": 준공 경과년수 기준 노후도.
- "주차": 세대당 주차대수 기준 편의.
- "시세_안정성": 매매 하한~상한 스프레드로 본 가격 안정성(담보 평가 신뢰도).
- "단지_위상": 최고층·동수로 본 단지 위상.
- "종합_의견": 위 항목과 평균 점수, 주상복합 여부를 토대로 담보 적합성 종합.

작성 규칙:
- 각 값은 2~3문장의 한국어 존대형(~합니다) 평문. 마크다운/번호 금지.
- 제공된 수치(세대수/동수/층/주차/점수/시세)만 사용. 임의 수치·주변환경 추측 금지."""


def _complex_avg(scores: ComplexScores) -> int:
    return round((scores.scale + scores.age + scores.parking
                  + scores.price_stability + scores.landmark) / 5)


def _won_eok(v: Optional[int]) -> str:
    return f"{v / 1e8:.2f}억" if v and v > 0 else "확인 불가"


def _fallback_complex(scores: ComplexScores) -> str:
    return (
        f"[종합 의견] AI 자동 분석 일시 사용 불가. 산출된 단지 특성 점수 평균 "
        f"{_complex_avg(scores)}점을 참고하시기 바랍니다."
    )


def build_complex_prompt(complex_name, scores, master, credit, pyeong) -> str:
    from services.complex_score_service import _year_int

    m = master or {}
    units = m.get("total_households")
    parking = m.get("total_parking")
    by = _year_int(m.get("built_year"))
    age_txt = f"{datetime.now().year - by}년 (준공 {by}년)" if by else "정보없음"
    per_txt = f"{parking / units:.2f}대/세대" if parking and units else "정보없음"
    mixed = scores.is_mixed_use
    mixed_txt = "주상복합" if mixed else ("일반 아파트" if mixed is False else "미상")
    kb = credit.kb_price if credit else None
    price_txt = (
        f"하한 {_won_eok(kb.low)} / 일반 {_won_eok(kb.estimated)} / 상한 {_won_eok(kb.high)}"
        if kb else "확인 불가"
    )

    return f"""다음 단지의 담보 특성 분석을 작성하세요.

[단지 기본]
- 단지명: {complex_name or "-"}
- 세대수: {units or "정보없음"}세대
- 총 동수: {m.get("total_buildings") or "정보없음"}동
- 최고층: {m.get("max_floor") or "정보없음"}층
- 연식: {age_txt}
- 세대당 주차: {per_txt}
- 복도타입: {m.get("corridor_type") or "-"}
- 물건유형: {mixed_txt}
- 평형: {pyeong}평 (전용)

[KB 시세]
{price_txt}

[단지 특성점수 — 0~100]
- 단지 규모: {scores.scale}
- 연식: {scores.age}
- 주차 편의: {scores.parking}
- 시세 안정성: {scores.price_stability}
- 단지 위상: {scores.landmark}
- 평균: {_complex_avg(scores)}점

위 사실만 사용해 다음 6개 키를 모두 포함한 JSON 객체로 응답하세요. 키 이름은 정확히 그대로:
{{"단지_규모": "...", "연식": "...", "주차": "...", "시세_안정성": "...", "단지_위상": "...", "종합_의견": "..."}}
"""


def generate_or_get_cached_complex(
    db: Session,
    application_id: Optional[str],
    *,
    complex_name: Optional[str],
    scores: ComplexScores,
    master: Optional[dict],
    credit,
    pyeong: Optional[int] = None,
) -> str:
    """내부망 단지특성 분석 — 캐시 우선(ai_analysis_text), 없으면 OpenAI 호출. 실패 시 fallback."""
    app = None
    if application_id:
        app = db.query(LoanApplication).filter(LoanApplication.id == application_id).first()
        if app and app.ai_analysis_text:
            logger.info(f"[ai_analysis] cache hit (complex) for application {application_id}")
            return app.ai_analysis_text

    prompt = build_complex_prompt(complex_name, scores, master, credit, pyeong)
    try:
        from services.llm_service import LLMClient
        from services.prompt_registry import get_prompt

        client = LLMClient()
        system_prompt = get_prompt(db, "property", "system_internal", COMPLEX_SYSTEM_PROMPT)
        result = client.complete(prompt, system=system_prompt, json_mode=True)
        raw = (result.get("text") or "").strip()
        if not raw:
            return _fallback_complex(scores)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"[ai_analysis] complex JSON parse failed: {e}; raw[:200]={raw[:200]}")
            return _fallback_complex(scores)

        text = _assemble(parsed, [
            ("[단지 규모]", "단지_규모"),
            ("[연식]", "연식"),
            ("[주차]", "주차"),
            ("[시세 안정성]", "시세_안정성"),
            ("[단지 위상]", "단지_위상"),
            ("[종합 의견]", "종합_의견"),
        ])
        if not text:
            return _fallback_complex(scores)

        if app:
            app.ai_analysis_text = text
            app.ai_analysis_generated_at = datetime.utcnow()
            db.commit()
            logger.info(
                f"[ai_analysis] complex generated and cached for application {application_id} "
                f"(tokens: in={result.get('prompt_tokens')}, out={result.get('completion_tokens')})"
            )
        return text
    except Exception as e:
        logger.warning(f"[ai_analysis] complex LLM call failed: {e}")
        return _fallback_complex(scores)
