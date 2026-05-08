from pydantic import BaseModel
from typing import Dict, Optional, List


class YearlyFinancial(BaseModel):
    """연도별 재무 정보"""
    year: int
    assets: int  # 자산
    liabilities: int  # 부채
    equity: int  # 자본
    revenue: int  # 매출
    operating_profit: int  # 영업이익
    net_income: int  # 당기순이익


class BorrowerInfo(BaseModel):
    """차주 정보"""
    company_name: str  # 대부업체 명칭
    business_number: str
    financial_data: List[YearlyFinancial]  # 최근 3년 재무 데이터


class GuarantorInfo(BaseModel):
    """연대보증인 정보"""
    name: str
    credit_score_kcb: int
    credit_score_nice: int
    direct_debt: int
    guarantee_debt: int


class PropertyBasicInfo(BaseModel):
    """담보 물건 기초 정보"""
    complex_name: Optional[str] = None
    units: Optional[int] = None
    corridor_type: Optional[str] = None
    age: Optional[int] = None
    area: Optional[int] = None  # 전용평형 (호환용)
    exclusive_m2: Optional[float] = None
    supply_m2: Optional[float] = None
    location_score: Optional[int] = None
    address: str


class OwnershipEntry(BaseModel):
    """소유지분현황 (갑구)"""
    name: str
    reg_number: str
    share: str
    address: str
    rank_number: int

class OwnershipOtherEntry(BaseModel):
    """소유지분 제외 소유권 사항 (갑구)"""
    rank_number: int
    purpose: str
    receipt_info: str
    details: str

class MortgageEntry(BaseModel):
    """(근)저당권 및 전세권 등 (을구)"""
    rank_number: str
    purpose: str
    receipt_info: str
    main_details: str
    target_owner: str

class RightsAnalysisDetail(BaseModel):
    """AI 권리 분석 - 항목별 요약"""
    gap_summary: str     # 갑구 요약
    eul_summary: str     # 을구 요약
    seizure_summary: str # 가압류 요약
    priority_summary: str # 선순위 요약

class PropertyRightsInfo(BaseModel):
    """담보 물건 권리 정보"""
    ownership_entries: list  # 소유지분현황 (갑구)
    ownership_other_entries: list  # 소유지분 제외 소유권 사항 (갑구)
    mortgage_entries: list  # (근)저당권 및 전세권 등 (을구)
    max_bond_amount: int  # 선순위 채권최고액 (원)
    tenant_deposit: int   # 선순위 임차보증금 (원)


class PricePoint(BaseModel):
    """가격 데이터 포인트"""
    date: str
    price: int


class KBPrice(BaseModel):
    """KB 시세 정보"""
    estimated: int
    high: int
    low: int
    trend: str
    history: List[PricePoint]  # 최근 3개월 시계열 데이터


class MOLITTransactions(BaseModel):
    """국토교통부 실거래가 정보"""
    recent_price: int
    transaction_date: str
    trend: str
    history: List[PricePoint]  # 최근 3개월 실거래가 (여러 건)


class NaverListings(BaseModel):
    """네이버 매매호가 정보"""
    avg_asking: int
    listing_count: int
    trend: str
    history: List[PricePoint]  # 최근 3개월 호가 (여러 건)


class ForecastPoint(BaseModel):
    """JB 시세 미래 예측 (90% 신뢰구간)"""
    date: str       # YYYY-MM-DD
    predicted: int  # 중심선
    lower: int      # 신뢰구간 하한
    upper: int      # 신뢰구간 상한


class JBFairPriceDetail(BaseModel):
    """JB 적정시세 동적 가중치 산출 상세"""
    fair_price: int
    weights: Dict[str, float]      # {kb, molit, naver} — 정규화된 가중치
    sources: Dict[str, int]        # 각 소스 대표값
    confidence: Dict[str, float]   # 정규화 전 신뢰도
    notes: List[str]               # 산출 근거
    history: List[PricePoint] = []  # JB 시점별 추이
    forecast: List[ForecastPoint] = []  # 미래 12개월 예측 (90% CI)


class CreditData(BaseModel):
    """크레딧 데이터"""
    kb_price: KBPrice
    molit_transactions: MOLITTransactions
    naver_listings: NaverListings
    jb_fair_price: Optional[int] = None
    jb_detail: Optional[JBFairPriceDetail] = None  # 1단계 동적 가중치 산출 상세


class LocationScores(BaseModel):
    """입지 분석 레이더 차트 점수"""
    station_walk: int       # 인접 역까지 도보 소요 시간 점수 (0~100)
    commute_time: int       # 주요 업무지구 평균 소요 시간 점수 (0~100)
    school_walk: int        # 인접 초등학교까지 도보 소요 시간 점수 (0~100)
    units_score: int        # 세대 수 점수 (0~100)
    living_env: int         # 생활환경 점수 (0~100)
    nature_env: int         # 자연환경 점수 (0~100)


class AIAnalysis(BaseModel):
    """AI 분석 결과"""
    property_analysis: str
    rights_analysis: RightsAnalysisDetail
    market_analysis: str
    nearby_analysis: Optional[str] = None
    comprehensive_opinion: Optional[str] = None
    auditor_recommendation: Optional[str] = None  # 심사역 권고 의견 초안
    location_scores: Optional[LocationScores] = None


class SimilarProperty(BaseModel):
    """인근 유사 물건"""
    name: str
    sido: str
    sigungu: str
    address: str
    units: int
    age: int
    area: int                          # 비교 면적 (평)
    exclusive_m2: Optional[float] = None
    lat: float
    lng: float
    distance_m: Optional[int] = None   # 타겟 단지로부터의 거리 (m)
    similarity: Optional[float] = None # 유사도 점수 (0~1)
    recent_price: int
    price_change_rate: float
    price_diff_pct: Optional[float] = None  # 타겟 vs 유사물건 가격차 (% — 양수=유사물건이 더 비쌈)


class NearbyPropertyTrends(BaseModel):
    """인근 유사 물건지 동향"""
    target_lat: float
    target_lng: float
    target_recent_price: Optional[int] = None  # 비교 기준이 되는 타겟 단지 최근 거래가
    radius_m: Optional[int] = None              # 적용된 검색 반경
    avg_change_rate: Optional[float] = None     # 인근 평균 변동률
    similar_properties: List[SimilarProperty]


class PricePerPyeongPoint(BaseModel):
    """평단가 데이터 포인트"""
    date: str
    complex: int
    dong: int
    sigungu: int


class PricePerPyeongTrend(BaseModel):
    """평단가 추이 데이터"""
    complex_name: str
    dong_name: str
    sigungu_name: str
    data: List[PricePerPyeongPoint]


class AnalysisData(BaseModel):
    """분석 데이터"""
    borrower_info: BorrowerInfo
    guarantor_info: GuarantorInfo
    property_basic_info: PropertyBasicInfo
    property_rights_info: PropertyRightsInfo
    credit_data: CreditData
    ai_analysis: AIAnalysis
    nearby_property_trends: Optional[NearbyPropertyTrends] = None
    price_per_pyeong_trend: Optional[PricePerPyeongTrend] = None


class AnalysisResponse(BaseModel):
    """분석 응답"""
    status: str
    data: AnalysisData
