"""LLM(OpenAI ChatCompletion) 분석용 프롬프트 템플릿"""


PROPERTY_ANALYSIS_PROMPT = """당신은 부동산 담보대출 심사를 위한 입지 분석 전문가입니다.
아래 물건 정보를 바탕으로, 담보 물건의 입지 적격성을 종합 분석해주세요.

[물건 기본 정보]
- 담보주소: {address}
- 세대수: {units}세대
- 준공년도: 약 {age}년 전
- 전용면적: {area}평
- 복도타입: {corridor_type}
- 입지점수: {location_score}/100

[분석 항목 - 반드시 아래 항목별로 평가해주세요]

1. 교통 접근성 (역세권 / 업무지구)
   - 역세권: 가장 가까운 지하철역까지 도보 소요시간 및 노선 수 평가
   - GBD(강남 업무지구): 대중교통 기준 접근 소요시간 및 편의성
   - CBD(도심 업무지구 - 종로/광화문): 대중교통 기준 접근 소요시간
   - YBD(여의도 업무지구): 대중교통 기준 접근 소요시간

2. 학군 / 교육환경
   - 초품아(단지 내 초등학교 배정 가능 여부)
   - 학권가(인근 학원가 밀집도, 학원 접근성)
   - 중·고등학교 학군 선호도

3. 단지 특성
   - 세대수: 대단지(1,000세대+) 여부 및 관리 여건
   - 연식: 경과 연수 대비 잔존 내용연수, 리모델링/재건축 가능성
   - 브랜드: 시공사 브랜드 등급(1군/2군) 및 시장 선호도
   - 커뮤니티시설: 피트니스, 독서실, 게스트하우스 등 단지 내 편의시설

4. 생활환경 / 자연환경
   - 마트: 대형마트 접근성 (도보/차량 소요시간)
   - 숲세권: 공원, 산책로, 녹지 접근성
   - 물세뷰: 강, 호수, 바다 조망 가능 여부 및 프리미엄
   - 문화시설: 도서관, 복합문화센터, 영화관 등 접근성

5. 전세가율 분석
   - 현재 전세가율(%) 및 실수요 기반 시장 안정성 판단

6. 종합 의견
   - 입지 종합 등급 (S/A/B/C/D)
   - 담보물건으로서의 입지 적격성 최종 판단
   - 특이사항 및 리스크 요인

각 항목별로 구체적인 수치나 근거를 포함하여 분석해주세요.
전체 500자 이내로 요약해주세요."""


RIGHTS_ANALYSIS_PROMPT = """당신은 등기부등본 권리 분석 전문가입니다.
다음 등기 정보를 분석해주세요:

갑구: {gap_section}
을구: {eul_section}
가압류: {seizure}
선순위: {priority_rank}순위

분석 내용:
1. 근저당 설정 상태
2. 선순위 권리 현황
3. 권리 리스크 평가

150자 이내로 요약해주세요."""


MARKET_ANALYSIS_PROMPT = """당신은 부동산 시세 분석 전문가입니다.
다음 시세 정보를 분석해주세요:

KB시세(추정가): {kb_estimated:,}원 (추세: {kb_trend})
국토부 실거래가: {molit_price:,}원 (추세: {molit_trend})
네이버 매매호가: {naver_price:,}원 (추세: {naver_trend})

대출신청금액: {loan_amount:,}원
예상 LTV: {ltv:.1f}%

분석 내용:
1. 시세 호가 모두 상승 국면 여부
2. 거래 추세 분석
3. 대출금액 대비 담보가치 평가 (LTV)

200자 이내로 요약해주세요."""


def format_property_prompt(property_info, address: str) -> str:
    """입지 분석 프롬프트 포맷팅"""
    return PROPERTY_ANALYSIS_PROMPT.format(
        address=address,
        units=property_info.units,
        age=property_info.age,
        area=property_info.area,
        corridor_type=property_info.corridor_type,
        location_score=property_info.location_score
    )


def format_rights_prompt(rights_info) -> str:
    """권리 분석 프롬프트 포맷팅"""
    return RIGHTS_ANALYSIS_PROMPT.format(
        gap_section=rights_info.gap_section,
        eul_section=rights_info.eul_section,
        seizure=rights_info.seizure if rights_info.seizure else "없음",
        priority_rank=rights_info.priority_rank
    )


def format_market_prompt(credit_data, loan_amount: int) -> str:
    """시세 분석 프롬프트 포맷팅"""
    kb_estimated = credit_data.kb_price.estimated
    ltv = (loan_amount / kb_estimated * 100) if kb_estimated > 0 else 0

    return MARKET_ANALYSIS_PROMPT.format(
        kb_estimated=credit_data.kb_price.estimated,
        kb_trend=credit_data.kb_price.trend,
        molit_price=credit_data.molit_transactions.recent_price,
        molit_trend=credit_data.molit_transactions.trend,
        naver_price=credit_data.naver_listings.avg_asking,
        naver_trend=credit_data.naver_listings.trend,
        loan_amount=loan_amount,
        ltv=ltv
    )
