import random
from datetime import date, timedelta
from models.response_models import (
    BorrowerInfo, GuarantorInfo, PropertyBasicInfo,
    PropertyRightsInfo, CreditData, KBPrice,
    MOLITTransactions, NaverListings, YearlyFinancial,
    PricePoint, LocationScores,
    SimilarProperty, NearbyPropertyTrends,
    PricePerPyeongPoint, PricePerPyeongTrend,
    OwnershipEntry, OwnershipOtherEntry, MortgageEntry, RightsAnalysisDetail
)


# 한국 이름 샘플
GUARANTOR_NAMES = ["홍길동", "신유진", "임재현", "송미라", "한동훈", "백지영", "오세훈", "남궁민"]

# 지역별 가격 배율
AREA_MULTIPLIERS = {
    "강남": 1.5,
    "서초": 1.4,
    "송파": 1.2,
    "양천": 1.0,
    "마포": 1.1,
    "용산": 1.3,
    "성동": 1.0,
    "강서": 0.9,
    "노원": 0.8,
    "은평": 0.85,
    "강북": 0.75,
    "도봉": 0.75
}


def parse_area_from_address(address: str) -> str:
    """주소에서 지역 추출"""
    for area in AREA_MULTIPLIERS.keys():
        if area in address:
            return area
    return "기타"


def generate_borrower_info(company_name: str) -> BorrowerInfo:
    """차주 정보 생성 (대부업체 3년 재무 데이터)"""
    current_year = date.today().year

    # 기준 재무 규모 설정 (억 단위)
    base_assets = random.randint(500, 2000)  # 500억~2000억

    financial_data = []
    for i in range(3):
        year = current_year - (2 - i)  # Y-2, Y-1, Y

        # 연도별 성장률 적용 (5%~15% 성장)
        growth_rate = 1 + random.uniform(0.05, 0.15) * i

        assets = int(base_assets * growth_rate * 100000000)
        liabilities = int(assets * random.uniform(0.4, 0.7))  # 부채비율 40~70%
        equity = assets - liabilities
        revenue = int(assets * random.uniform(0.3, 0.5))  # 매출 = 자산의 30~50%
        operating_profit = int(revenue * random.uniform(0.1, 0.25))  # 영업이익률 10~25%
        net_income = int(operating_profit * random.uniform(0.6, 0.85))  # 당기순이익 = 영업이익의 60~85%

        financial_data.append(YearlyFinancial(
            year=year,
            assets=assets,
            liabilities=liabilities,
            equity=equity,
            revenue=revenue,
            operating_profit=operating_profit,
            net_income=net_income
        ))

    return BorrowerInfo(
        company_name=company_name,
        business_number=f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(10000, 99999)}",
        financial_data=financial_data
    )


def generate_guarantor_info() -> GuarantorInfo:
    """연대보증인 정보 생성"""
    kcb = random.randint(700, 950)
    nice = kcb + random.randint(-30, 30)
    nice = max(0, min(1000, nice))
    return GuarantorInfo(
        name=random.choice(GUARANTOR_NAMES),
        credit_score_kcb=kcb,
        credit_score_nice=nice,
        direct_debt=random.randint(0, 100000000),
        guarantee_debt=random.randint(0, 50000000)
    )


def generate_property_basic_info(
    address: str,
    complex_name: str | None = None,
    pyeong: int | None = None,
) -> PropertyBasicInfo:
    """매칭 실패 시 폴백.

    크롤링 가능한 항목(세대수/복도타입/연식)은 임의 생성하지 않고 None(N/A).
    평수는 신청자가 입력한 값(pyeong)을 사용. 입지점수만 지역 기반 추정값.
    """
    area = parse_area_from_address(address)
    if area in ["강남", "서초", "송파"]:
        location_score = random.randint(85, 98)
    elif area == "기타":
        location_score = random.randint(60, 80)
    else:
        location_score = random.randint(70, 90)

    return PropertyBasicInfo(
        complex_name=complex_name,
        units=None,           # 크롤링 영역 → 데이터 없으면 N/A
        corridor_type=None,   # 크롤링 영역
        age=None,             # 크롤링 영역
        area=pyeong,          # 신청자 입력값
        location_score=location_score,  # 생성값 (지리 API 미연동)
        address=address,
    )


OWNER_NAMES = ["정미자", "김영수", "이정희", "박성호", "최은주", "한상민", "윤서연", "장현우"]

def generate_property_rights_info(address: str | None = None) -> PropertyRightsInfo:
    """담보 물건 권리 정보 생성 (등기부등본 주요 등기사항 요약 기반).

    address가 주어지면 소유자 주소를 동일 지역으로 생성 (지역 일관성 유지).
    """
    banks = ["KB국민은행", "신한은행", "우리은행", "하나은행", "NH농협은행"]
    lenders = ["주식회사유캐피탈대부", "주식회사에이원대부", "주식회사파란캐피탈대부"]

    owner_name = random.choice(OWNER_NAMES)
    reg_prefix = f"{random.randint(500, 900):03d}{random.randint(1, 12):02d}"

    # 소유자 주소: 입력된 담보주소를 기준으로 같은 지역 내 임의 주소 생성
    if address:
        district = parse_area_from_address(address)
        dong_list = DONG_NAMES.get(district, ["역삼동"])
        owner_dong = random.choice(dong_list)
        owner_addr = (
            f"서울 {district}구 {owner_dong} "
            f"{random.randint(50, 600)}-{random.randint(1, 30)} "
            f"{random.choice(COMPLEX_NAMES)} "
            f"{random.randint(101, 130)}-{random.randint(101, 2000)}"
        )
    else:
        owner_addr = (
            f"서울 강남구 역삼동 {random.randint(100, 800)}-{random.randint(1, 30)} "
            f"{random.choice(COMPLEX_NAMES)} {random.randint(101, 130)}-{random.randint(101, 2000)}"
        )

    # 1. 소유지분현황 (갑구)
    ownership_entries = [
        OwnershipEntry(
            name=f"{owner_name} (소유자)",
            reg_number=f"{reg_prefix}-*******",
            share="단독소유",
            address=owner_addr,
            rank_number=1
        )
    ]

    # 2. 소유지분 제외 소유권 사항 (갑구) - 80% 확률로 기록사항 없음
    ownership_other_entries = []
    if random.random() > 0.8:
        ownership_other_entries.append(
            OwnershipOtherEntry(
                rank_number=2,
                purpose="가압류",
                receipt_info=f"{random.randint(2023,2025)}년{random.randint(1,12)}월{random.randint(1,28)}일 제{random.randint(10000,99999)}호",
                details=f"채권자: ○○건설 주식회사\n청구금액: 금{random.randint(3000,8000)}만원"
            )
        )

    # 3. (근)저당권 및 전세권 등 (을구)
    mortgage_amount = random.randint(5, 10) * 100000000  # 5~10억
    mortgage_bank = random.choice(lenders)
    receipt_year = random.randint(2024, 2026)
    receipt_month = random.randint(1, 12)
    receipt_day = random.randint(1, 28)
    receipt_no = random.randint(100000, 999999)

    mortgage_entries = [
        MortgageEntry(
            rank_number=str(random.randint(5, 10)),
            purpose="근저당권설정",
            receipt_info=f"{receipt_year}년{receipt_month}월{receipt_day}일\n제{receipt_no}호",
            main_details=f"채권최고액 금{mortgage_amount:,}원\n근저당권자 {mortgage_bank}",
            target_owner=owner_name
        ),
        MortgageEntry(
            rank_number=f"{random.randint(5, 10)}-1",
            purpose="근질권",
            receipt_info=f"{receipt_year}년{receipt_month}월{receipt_day}일\n제{receipt_no + 1}호",
            main_details=f"채권최고액 금{mortgage_amount:,}원\n채권자 제이비우리캐피탈주식회사",
            target_owner=owner_name
        )
    ]

    # LTV 계산용: 채권최고액 = 선순위 근저당, 임차보증금 = 0.5~1.5억
    max_bond_amount = mortgage_amount
    tenant_deposit = random.choice([50000000, 80000000, 100000000, 120000000, 150000000])

    return PropertyRightsInfo(
        ownership_entries=[e.model_dump() for e in ownership_entries],
        ownership_other_entries=[e.model_dump() for e in ownership_other_entries],
        mortgage_entries=[e.model_dump() for e in mortgage_entries],
        max_bond_amount=max_bond_amount,
        tenant_deposit=tenant_deposit
    )


def generate_credit_data(address: str, base_price: int = None) -> CreditData:
    """크레딧 데이터 생성 (최근 3개월 시계열 포함)"""
    area = parse_area_from_address(address)
    multiplier = AREA_MULTIPLIERS.get(area, 1.0)

    # 기준 가격 (8억 ~ 15억)
    if base_price is None:
        base_price = int(random.randint(800000000, 1500000000) * multiplier)

    # 최근 3개월 시계열 데이터 생성
    today = date.today()

    # KB 시세 히스토리 (일별 단일 값)
    kb_history = []
    kb_current = base_price
    for i in range(90, -1, -1):  # 90일 전부터 오늘까지
        price_date = today - timedelta(days=i)
        # 약간의 변동 추가 (±2% 이내)
        kb_current = int(kb_current * random.uniform(0.98, 1.02))
        kb_history.append(PricePoint(
            date=price_date.strftime("%Y-%m-%d"),
            price=kb_current
        ))

    kb_estimated = kb_history[-1].price
    kb_high = int(kb_estimated * 1.08)
    kb_low = int(kb_estimated * 0.92)
    kb_trend = random.choice(["상승세", "안정적", "하락세"])

    # 국토부 실거래가 히스토리 (랜덤 거래 10~20건)
    molit_history = []
    transaction_count = random.randint(10, 20)
    for _ in range(transaction_count):
        days_ago = random.randint(0, 90)
        price_date = today - timedelta(days=days_ago)
        transaction_price = int(base_price * random.uniform(0.85, 1.05))
        molit_history.append(PricePoint(
            date=price_date.strftime("%Y-%m-%d"),
            price=transaction_price
        ))

    # 날짜순 정렬
    molit_history.sort(key=lambda x: x.date)
    molit_price = molit_history[-1].price if molit_history else int(base_price * 0.95)
    recent_date = molit_history[-1].date if molit_history else today.strftime("%Y-%m-%d")
    molit_trend = random.choice(["상승세", "안정적", "하락세"])

    # 네이버 매매호가 히스토리 (매물 15~30건)
    naver_history = []
    listing_count = random.randint(15, 30)
    for _ in range(listing_count):
        days_ago = random.randint(0, 90)
        price_date = today - timedelta(days=days_ago)
        asking_price = int(base_price * random.uniform(1.00, 1.15))
        naver_history.append(PricePoint(
            date=price_date.strftime("%Y-%m-%d"),
            price=asking_price
        ))

    # 날짜순 정렬
    naver_history.sort(key=lambda x: x.date)
    naver_asking = int(sum(p.price for p in naver_history[-5:]) / 5) if len(naver_history) >= 5 else int(base_price * 1.08)
    naver_trend = random.choice(["활발", "보통", "저조"])

    return CreditData(
        kb_price=KBPrice(
            estimated=kb_estimated,
            high=kb_high,
            low=kb_low,
            trend=kb_trend,
            history=kb_history
        ),
        molit_transactions=MOLITTransactions(
            recent_price=molit_price,
            transaction_date=recent_date,
            trend=molit_trend,
            history=molit_history
        ),
        naver_listings=NaverListings(
            avg_asking=naver_asking,
            listing_count=len(naver_history),
            trend=naver_trend,
            history=naver_history
        )
    )


def generate_location_scores(address: str) -> LocationScores:
    """입지 분석 레이더 차트 점수 생성"""
    area = parse_area_from_address(address)

    # 지역별 기본 점수 프로파일
    area_profiles = {
        "강남": {"station": (85, 98), "commute": (85, 95), "school": (80, 95), "units": (80, 95), "living": (85, 98), "nature": (60, 80)},
        "서초": {"station": (80, 95), "commute": (80, 93), "school": (82, 95), "units": (75, 90), "living": (82, 95), "nature": (70, 88)},
        "송파": {"station": (78, 93), "commute": (75, 90), "school": (80, 93), "units": (80, 95), "living": (80, 93), "nature": (72, 90)},
        "용산": {"station": (82, 95), "commute": (82, 95), "school": (70, 85), "units": (65, 85), "living": (80, 93), "nature": (75, 90)},
        "마포": {"station": (80, 95), "commute": (78, 90), "school": (72, 88), "units": (70, 88), "living": (78, 92), "nature": (65, 82)},
        "성동": {"station": (78, 92), "commute": (75, 88), "school": (70, 85), "units": (68, 85), "living": (75, 90), "nature": (70, 85)},
        "양천": {"station": (72, 88), "commute": (68, 82), "school": (78, 92), "units": (75, 90), "living": (75, 88), "nature": (68, 82)},
        "강서": {"station": (68, 85), "commute": (60, 78), "school": (72, 88), "units": (70, 88), "living": (70, 85), "nature": (65, 80)},
        "노원": {"station": (72, 88), "commute": (55, 72), "school": (75, 90), "units": (78, 92), "living": (68, 82), "nature": (78, 93)},
        "은평": {"station": (65, 82), "commute": (58, 75), "school": (72, 85), "units": (65, 82), "living": (68, 82), "nature": (80, 95)},
        "강북": {"station": (68, 85), "commute": (60, 75), "school": (70, 85), "units": (65, 82), "living": (65, 80), "nature": (75, 92)},
        "도봉": {"station": (70, 86), "commute": (52, 70), "school": (72, 88), "units": (72, 88), "living": (65, 80), "nature": (80, 95)},
    }

    default_profile = {"station": (65, 85), "commute": (55, 78), "school": (65, 85), "units": (60, 82), "living": (65, 82), "nature": (65, 85)}
    profile = area_profiles.get(area, default_profile)

    return LocationScores(
        station_walk=random.randint(*profile["station"]),
        commute_time=random.randint(*profile["commute"]),
        school_walk=random.randint(*profile["school"]),
        units_score=random.randint(*profile["units"]),
        living_env=random.randint(*profile["living"]),
        nature_env=random.randint(*profile["nature"])
    )


# 지역별 중심 좌표
DISTRICT_CENTERS = {
    "강남": (37.5172, 127.0473),
    "서초": (37.4837, 127.0324),
    "송파": (37.5145, 127.1060),
    "양천": (37.5270, 126.8563),
    "마포": (37.5663, 126.9019),
    "용산": (37.5326, 126.9909),
    "성동": (37.5634, 127.0371),
    "강서": (37.5510, 126.8495),
    "노원": (37.6542, 127.0568),
    "은평": (37.6027, 126.9291),
    "강북": (37.6396, 127.0255),
    "도봉": (37.6688, 127.0471),
}

# 아파트 단지명 샘플
COMPLEX_NAMES = [
    "래미안", "자이", "힐스테이트", "e편한세상", "롯데캐슬",
    "SK뷰", "더샵", "아이파크", "푸르지오", "한신더휴",
    "동부센트레빌", "현대아이파크", "대림아크로리버",
    "삼성래미안", "GS자이", "대우푸르지오", "현대힐스테이트",
    "두산위브"
]

# 구별 동 이름
DONG_NAMES = {
    "강남": ["대치동", "삼성동", "역삼동", "청담동", "논현동", "도곡동"],
    "서초": ["반포동", "잠원동", "서초동", "방배동", "양재동"],
    "송파": ["잠실동", "문정동", "가락동", "석촌동", "방이동"],
    "양천": ["목동", "신정동", "신월동"],
    "마포": ["상암동", "합정동", "망원동", "연남동", "성산동"],
    "용산": ["이촌동", "한남동", "이태원동", "서빙고동"],
    "성동": ["성수동", "옥수동", "금호동", "행당동"],
    "강서": ["화곡동", "등촌동", "방화동", "마곡동"],
    "노원": ["상계동", "중계동", "하계동", "월계동"],
    "은평": ["불광동", "녹번동", "응암동", "진관동"],
    "강북": ["미아동", "번동", "수유동", "우이동", "삼양동"],
    "도봉": ["창동", "도봉동", "쌍문동", "방학동"],
}


def generate_nearby_property_trends(address: str, property_basic_info: PropertyBasicInfo) -> NearbyPropertyTrends:
    """인근 유사 물건지 동향 데이터 생성"""
    area = parse_area_from_address(address)
    center = DISTRICT_CENTERS.get(area, (37.5665, 126.9780))  # 기본값: 서울 시청

    # 대상 물건 좌표 (중심에서 약간 오프셋)
    target_lat = center[0] + random.uniform(-0.003, 0.003)
    target_lng = center[1] + random.uniform(-0.003, 0.003)

    multiplier = AREA_MULTIPLIERS.get(area, 1.0)
    base_price = int(random.randint(800000000, 1500000000) * multiplier)
    dong_list = DONG_NAMES.get(area, ["역삼동", "대치동", "삼성동"])

    similar_properties = []
    used_names = set()
    for _ in range(5):
        # 겹치지 않는 단지명 선택
        name = random.choice(COMPLEX_NAMES)
        while name in used_names:
            name = random.choice(COMPLEX_NAMES)
        used_names.add(name)

        dong = random.choice(dong_list)
        sido = "서울특별시"
        sigungu = f"{area}구"
        prop_address = f"{sido} {sigungu} {dong}"

        # 유사 세대수 (±200), 유사 연식 (±5년)
        base_units = property_basic_info.units or 500
        base_age = property_basic_info.age or 15
        sim_units = max(100, base_units + random.randint(-200, 200))
        sim_age = max(1, base_age + random.randint(-5, 5))
        sim_area = random.choice([24, 29, 34, 39, 42, 51, 59])

        # 좌표: 대상 물건 주변 약 300~500m 반경
        sim_lat = target_lat + random.uniform(-0.004, 0.004)
        sim_lng = target_lng + random.uniform(-0.004, 0.004)

        sim_price = int(base_price * random.uniform(0.85, 1.15))
        change_rate = round(random.uniform(-0.05, 0.08), 3)

        similar_properties.append(SimilarProperty(
            name=f"{name} {dong}",
            sido=sido,
            sigungu=sigungu,
            address=prop_address,
            units=sim_units,
            age=sim_age,
            area=sim_area,
            lat=sim_lat,
            lng=sim_lng,
            recent_price=sim_price,
            price_change_rate=change_rate
        ))

    return NearbyPropertyTrends(
        target_lat=target_lat,
        target_lng=target_lng,
        similar_properties=similar_properties
    )


def generate_price_per_pyeong_trend(address: str, base_price: int, area_pyeong: int) -> PricePerPyeongTrend:
    """단지/읍면동/시군구 평단가 추이 데이터 생성"""
    district = parse_area_from_address(address)
    dong_list = DONG_NAMES.get(district, ["역삼동"])
    dong_name = random.choice(dong_list)
    sigungu_name = f"{district}구" if district != "기타" else "서울시"

    # 단지명 생성
    complex_name = f"{random.choice(COMPLEX_NAMES)} {dong_name}"

    # 기준 평단가 (만원/평)
    base_pyeong_price = int(base_price / area_pyeong / 10000)

    today = date.today()
    data = []
    for i in range(2, -1, -1):  # 2개월 전, 1개월 전, 이번 달
        month_date = today.replace(day=1) - timedelta(days=i * 30)
        month_str = month_date.strftime("%Y-%m")

        # 월별 변동 (±2%)
        month_factor = 1 + random.uniform(-0.02, 0.02) * (2 - i)

        complex_price = int(base_pyeong_price * month_factor)
        dong_price = int(base_pyeong_price * month_factor * random.uniform(0.90, 1.05))
        sigungu_price = int(base_pyeong_price * month_factor * random.uniform(0.80, 0.95))

        data.append(PricePerPyeongPoint(
            date=month_str,
            complex=complex_price,
            dong=dong_price,
            sigungu=sigungu_price
        ))

    return PricePerPyeongTrend(
        complex_name=complex_name,
        dong_name=dong_name,
        sigungu_name=sigungu_name,
        data=data
    )
