"""
KB부동산 API endpoint definitions.

2026-02-08 API 디스커버리 결과로 실제 엔드포인트 확인 완료.
JS 번들 분석 + 직접 호출 검증으로 확정된 값입니다.

Last verified: 2026-02-08 (api_discovery + JS bundle extraction)
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class KBEndpoint:
    """KB API 엔드포인트 정의"""
    name: str
    base_url: str
    path: str
    method: str  # GET or POST
    description: str

    @property
    def url(self) -> str:
        return f"{self.base_url}{self.path}"


# Base URLs
KB_API_BASE = "https://api.kbland.kr"

# ------------------------------------------------------------------
# 단지 검색/목록 관련
# ------------------------------------------------------------------

# 지도 영역 내 단지 목록 (메인 검색 API)
COMPLEX_SEARCH = KBEndpoint(
    name="complex_search",
    base_url=KB_API_BASE,
    path="/land-complex/map/map250mBlwInfoList",
    method="POST",
    description="지도 영역 내 단지 목록 (좌표 기반). 응답: dataBody.data.단지리스트[]",
)

# 단지 상세 정보
COMPLEX_DETAIL = KBEndpoint(
    name="complex_detail",
    base_url=KB_API_BASE,
    path="/land-complex/complex/main",
    method="GET",
    description="단지 상세 정보. 파라미터: 단지기본일련번호, 물건종류(01=아파트)",
)

# 단지 면적/타입 정보
COMPLEX_TYPE_INFO = KBEndpoint(
    name="complex_type_info",
    base_url=KB_API_BASE,
    path="/land-complex/complex/typInfo",
    method="GET",
    description="단지별 면적 타입 목록. 파라미터: 단지기본일련번호. 응답: dataBody.data[]",
)

# ------------------------------------------------------------------
# 시세 (KB가격) 관련
# ------------------------------------------------------------------

# KB 시세 조회 (핵심 API - 검증 완료)
COMPLEX_PRICE = KBEndpoint(
    name="complex_price",
    base_url=KB_API_BASE,
    path="/land-price/price/BasePrcInfoNew",
    method="GET",
    description="단지별 KB 시세. 파라미터: 단지기본일련번호, 면적일련번호. "
                "응답: dataBody.data.시세[].{매매일반거래가, 매매상한가, 매매하한가, 시세기준년월일}",
)

# ------------------------------------------------------------------
# 실거래가 관련
# ------------------------------------------------------------------

# 실거래가 상세 조회
COMPLEX_TRANSACTION = KBEndpoint(
    name="complex_transaction",
    base_url=KB_API_BASE,
    path="/land-complex/vlaHscmDtail/vlaDealDtailPriceInq",
    method="GET",
    description="단지별 실거래가. 파라미터: 단지기본일련번호, 면적일련번호, 거래유형(1=매매)",
)

# 연도별 과거 실거래가
COMPLEX_TRANSACTION_YEARLY = KBEndpoint(
    name="complex_transaction_yearly",
    base_url=KB_API_BASE,
    path="/land-complex/vlaHscmDtail/vlaDealPricePastYearInq",
    method="GET",
    description="연도별 과거 실거래가. 파라미터: 단지기본일련번호, 면적일련번호, 거래유형",
)

# ------------------------------------------------------------------
# 매물 관련
# ------------------------------------------------------------------

# 매물 목록 (지도 영역 기반 - 미사용)
COMPLEX_LISTING = KBEndpoint(
    name="complex_listing",
    base_url=KB_API_BASE,
    path="/land-property/propList/stutCdFilter",
    method="POST",
    description="매물 목록 (좌표 기반). 파라미터: selectCode, zoomLevel, startLat/Lng, endLat/Lng 등",
)

# 단지 브리프 정보 (매물 조회의 선행 API)
COMPLEX_BRIF = KBEndpoint(
    name="complex_brif",
    base_url=KB_API_BASE,
    path="/land-complex/complex/brif",
    method="GET",
    description="단지 브리프 정보. 파라미터: 단지기본일련번호. propList/main의 POST body로 사용.",
)

# 단지별 매물 목록 (실제 개별 매물 데이터)
COMPLEX_PROP_LIST = KBEndpoint(
    name="complex_prop_list",
    base_url=KB_API_BASE,
    path="/land-property/propList/main",
    method="POST",
    description="단지별 매물 목록. brif 데이터 + 페이지 파라미터를 POST body로 전송. 응답: propertyList[]",
)

# 단지별 매물 건수
COMPLEX_LISTING_COUNT = KBEndpoint(
    name="complex_listing_count",
    base_url=KB_API_BASE,
    path="/land-complex/complexResteBrhs/propCountByTradeKind",
    method="GET",
    description="단지별 매물 건수. 파라미터: 단지기본일련번호. 응답: {매매건수, 전세건수, 월세건수}",
)

# ------------------------------------------------------------------
# 지역/행정구역 관련
# ------------------------------------------------------------------

# 시도별 시군구 목록
REGION_SIGUNGU = KBEndpoint(
    name="region_sigungu",
    base_url=KB_API_BASE,
    path="/land-complex/map/siGunGuAreaNameList",
    method="GET",
    description="시도별 시군구 목록. 파라미터: 시도명. 응답: [{법정동코드, 시군구명, wgs84좌표}]",
)

# 시군구별 법정동 목록
REGION_DONG = KBEndpoint(
    name="region_dong",
    base_url=KB_API_BASE,
    path="/land-complex/map/stutDongAreaNameList",
    method="GET",
    description="시군구별 법정동 목록. 파라미터: 시도명, 시군구명. 응답: [{법정동명, 법정동코드}]",
)

# ------------------------------------------------------------------
# 한글 파라미터명 상수 (API가 한글 키 사용)
# ------------------------------------------------------------------
PARAM_COMPLEX_NO = "단지기본일련번호"
PARAM_AREA_NO = "면적일련번호"
PARAM_PROPERTY_TYPE = "물건종류"  # "01"=아파트
PARAM_TRADE_TYPE = "거래유형"    # "1"=매매, "2"=전세, "3"=월세
PARAM_SIDO = "시도명"
PARAM_SIGUNGU = "시군구명"
