"""프롬프트 테스트용 샘플 입력.

관리자 UI 의 "테스트 실행" 패널에서 (feature_key, prompt_key) 별로 미리 준비된
샘플을 select 해서 빠르게 검증할 수 있다. 각 프롬프트마다 user 입력 형식이 다르므로
정적 dict 로 관리한다.

샘플 추가 방법: 아래 SAMPLES 에 (feature_key, prompt_key) 키로 list 를 추가.
각 항목은 {label, user_input, json_mode(optional)} 형식.
"""
from typing import TypedDict


class PromptSample(TypedDict, total=False):
    label: str
    user_input: str
    json_mode: bool


# 키: (feature_key, prompt_key)
SAMPLES: dict[tuple[str, str], list[PromptSample]] = {
    ("property", "system"): [
        {
            "label": "강남 25평 (기본)",
            "user_input": (
                '{"complex_name": "강남샘플아파트", "address": "서울시 강남구 대치동", '
                '"units": 1200, "age": 18, "pyeong": 25, "location_scores": '
                '{"station_walk": 90, "commute_time": 88, "school_walk": 80, '
                '"units_score": 85, "living_env": 92, "nature_env": 70}}'
            ),
        },
    ],
    ("market", "system"): [
        {
            "label": "KB·실거래·매물 종합",
            "user_input": (
                '{"complex_name": "샘플단지", "kb_estimated": 1100000000, '
                '"molit_recent": 1080000000, "naver_avg_asking": 1150000000, '
                '"trend_3m": "rising"}'
            ),
        },
    ],
    ("nearby", "system"): [
        {
            "label": "유사단지 5건 + 추이",
            "user_input": (
                '{"target": "샘플단지 25평", "similar": ['
                '{"name": "인근A", "distance_m": 320, "recent_price": 1050000000, '
                '"change_3m_pct": 1.2, "similarity": 0.82}, '
                '{"name": "인근B", "distance_m": 480, "recent_price": 1120000000, '
                '"change_3m_pct": -0.5, "similarity": 0.78}'
                ']}'
            ),
        },
    ],
    ("overall", "system"): [
        {
            "label": "분석 4종 통합",
            "user_input": (
                '{"property": "입지 양호, 학군 우수", "market": "최근 3개월 +1.5%", '
                '"nearby": "인근 평균 대비 +2%", "rights": "1순위 근저당 외 위험 없음", '
                '"loan_amount": 800000000, "kb_price": 1100000000, "ltv": 72.7}'
            ),
        },
    ],
    ("rights", "system"): [
        {
            "label": "단순 1순위 근저당",
            "user_input": (
                "# 등기부등본 (집합건물)\n\n"
                "## 갑구\n1. 소유권보존 - 홍길동\n2. 소유권이전 - 김철수 (2018-03-15)\n\n"
                "## 을구\n1. 근저당권설정 - 채권최고액 600,000,000원, 근저당권자 우리은행 "
                "(2018-03-15, 접수 제12345호)"
            ),
            "json_mode": True,
        },
    ],
    ("rights", "critique"): [
        {
            "label": "1차 결과 검증",
            "user_input": (
                '{"ownership_entries": [{"name": "김철수", "share": "단독", '
                '"rank_number": 2}], "mortgage_entries": [{"rank_number": "1", '
                '"main_details": "채권최고액 600,000,000원, 근저당권자 우리은행", '
                '"target_owner": "김철수"}], "max_bond_amount": 600000000, '
                '"tenant_deposit": 0}'
            ),
            "json_mode": True,
        },
    ],
}


def list_samples(feature_key: str, prompt_key: str) -> list[PromptSample]:
    return list(SAMPLES.get((feature_key, prompt_key), []))
