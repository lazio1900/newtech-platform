"""본 앱이 인지하는 표준 entity 목록.

외부 데이터 소스 매핑(DataSourceMapping)을 정의할 때, 어떤 logical entity 의
어떤 표준 필드로 매핑하는지 admin UI 에 표시·검증하기 위한 메타데이터.

Phase 2 에서 data_source_adapter 가 이 메타데이터 + DB 의 매핑 룰을 결합해
실제 동적 SELECT 를 만들어낼 예정.
"""
from typing import TypedDict


class StandardField(TypedDict):
    key: str
    type: str   # 'int' | 'str' | 'float' | 'date' | 'datetime' | 'bool'
    required: bool
    description: str


class EntityMeta(TypedDict):
    key: str
    label: str
    description: str
    fields: list[StandardField]


ENTITY_REGISTRY: dict[str, EntityMeta] = {
    "complex": {
        "key": "complex",
        "label": "단지",
        "description": "아파트 단지 마스터 (위치·세대수·연식 등)",
        "fields": [
            {"key": "id",               "type": "int",  "required": True,  "description": "단지 고유 ID"},
            {"key": "name",             "type": "str",  "required": True,  "description": "단지명"},
            {"key": "address",          "type": "str",  "required": True,  "description": "지번 주소"},
            {"key": "road_address",     "type": "str",  "required": False, "description": "도로명 주소"},
            {"key": "region_code",      "type": "str",  "required": True,  "description": "시군구 코드 (5자리)"},
            {"key": "dong_code",        "type": "str",  "required": False, "description": "법정동 코드 (10자리)"},
            {"key": "lat",              "type": "float","required": False, "description": "위도"},
            {"key": "lng",              "type": "float","required": False, "description": "경도"},
            {"key": "built_year",       "type": "str",  "required": False, "description": "준공연월 (예: '1999.11')"},
            {"key": "total_households", "type": "int",  "required": False, "description": "세대수"},
        ],
    },
    "area": {
        "key": "area",
        "label": "평형",
        "description": "단지별 평형 (전용/공급/평수)",
        "fields": [
            {"key": "id",           "type": "int",  "required": True,  "description": "평형 고유 ID"},
            {"key": "complex_id",   "type": "int",  "required": True,  "description": "소속 단지 ID"},
            {"key": "exclusive_m2", "type": "float","required": True,  "description": "전용면적 (㎡)"},
            {"key": "supply_m2",    "type": "float","required": False, "description": "공급면적 (㎡)"},
            {"key": "pyeong",       "type": "float","required": False, "description": "평수"},
        ],
    },
    "transaction": {
        "key": "transaction",
        "label": "실거래",
        "description": "국토부 실거래 (단지·평형·계약일·금액)",
        "fields": [
            {"key": "id",            "type": "int",  "required": True,  "description": "거래 고유 ID"},
            {"key": "complex_id",    "type": "int",  "required": True,  "description": "단지 ID"},
            {"key": "exclusive_m2",  "type": "float","required": True,  "description": "전용면적"},
            {"key": "contract_date", "type": "date", "required": True,  "description": "계약일"},
            {"key": "price",         "type": "int",  "required": True,  "description": "거래가 (원)"},
            {"key": "is_cancelled",  "type": "bool", "required": False, "description": "계약 해지 여부"},
        ],
    },
    "kb_price": {
        "key": "kb_price",
        "label": "KB 시세",
        "description": "KB 부동산 일반가·고가·저가",
        "fields": [
            {"key": "complex_id",      "type": "int",  "required": True,  "description": "단지 ID"},
            {"key": "area_id",         "type": "int",  "required": True,  "description": "평형 ID"},
            {"key": "as_of_date",      "type": "date", "required": True,  "description": "기준일"},
            {"key": "general_price",   "type": "int",  "required": False, "description": "일반가 (원)"},
            {"key": "high_avg_price",  "type": "int",  "required": False, "description": "상위 평균가"},
            {"key": "low_avg_price",   "type": "int",  "required": False, "description": "하위 평균가"},
        ],
    },
    "listing": {
        "key": "listing",
        "label": "매물 호가",
        "description": "네이버 등 매물 호가",
        "fields": [
            {"key": "complex_id", "type": "int",  "required": True,  "description": "단지 ID"},
            {"key": "area_id",    "type": "int",  "required": True,  "description": "평형 ID"},
            {"key": "ask_price",  "type": "int",  "required": True,  "description": "호가 (원)"},
            {"key": "status",     "type": "str",  "required": False, "description": "매물 상태"},
        ],
    },
}


# 변환 함수 카탈로그 — UI 에서 선택 가능 + 실제 어댑터(Phase 2)에서 적용
TRANSFORM_REGISTRY: list[dict] = [
    {"key": "none",              "label": "(변환 없음)",     "description": "그대로 사용"},
    {"key": "to_int",            "label": "→ 정수",           "description": "숫자 문자열·실수를 정수로"},
    {"key": "to_float",          "label": "→ 실수",           "description": "문자열·정수를 실수로"},
    {"key": "to_str",            "label": "→ 문자열",         "description": "타입 무관 문자열로"},
    {"key": "won_to_int",        "label": "원 단위 정수",     "description": "'1,234,000원' → 1234000"},
    {"key": "manwon_to_won",     "label": "만원 → 원",         "description": "12345 (만원) → 123450000"},
    {"key": "date_yyyymmdd",     "label": "YYYYMMDD → date",  "description": "'20240115' → date"},
    {"key": "date_iso",          "label": "ISO date 파싱",    "description": "'2024-01-15' → date"},
    {"key": "year_from_date",    "label": "연월 추출",         "description": "date·datetime → 'YYYY.MM'"},
    {"key": "bool_y_n",          "label": "Y/N → bool",       "description": "'Y'/'N' → True/False"},
]


def list_entities() -> list[EntityMeta]:
    return list(ENTITY_REGISTRY.values())


def get_entity(key: str) -> EntityMeta | None:
    return ENTITY_REGISTRY.get(key)


def list_transforms() -> list[dict]:
    return TRANSFORM_REGISTRY
