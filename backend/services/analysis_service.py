import logging
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from models.response_models import (
    AnalysisData, AnalysisResponse, AIAnalysis, RightsAnalysisDetail,
    PropertyBasicInfo,
)
from services.dummy_data import (
    generate_borrower_info,
    generate_guarantor_info,
    generate_property_basic_info,
    generate_property_rights_info,
    generate_credit_data,
    generate_location_scores,
    generate_nearby_property_trends,
    generate_price_per_pyeong_trend
)
from services.real_data_service import get_real_market_data

logger = logging.getLogger(__name__)

# TODO: Claude API 연동 시 아래 주석 해제
# from services.claude_service import ClaudeClient
# from utils.prompts import (
#     format_property_prompt,
#     format_rights_prompt,
#     format_market_prompt
# )


def _build_real_property_basic_info(
    complex_obj,
    area_obj,
    property_address: str,
) -> PropertyBasicInfo:
    """DB의 Complex/Area 데이터로 담보 물건 기초 정보를 구성한다."""
    units = complex_obj.total_households  # None이면 N/A
    corridor_type = complex_obj.corridor_type  # None이면 N/A

    age = None
    if complex_obj.build_year:
        age = date.today().year - complex_obj.build_year

    area_pyeong = None
    if area_obj:
        if area_obj.pyeong:
            area_pyeong = int(area_obj.pyeong)
        elif area_obj.exclusive_m2:
            area_pyeong = int(area_obj.exclusive_m2 / 3.305785)

    # location_score는 DB에 없음 (지리 API 필요) → None (N/A)
    return PropertyBasicInfo(
        address=complex_obj.address or property_address,
        units=units,
        corridor_type=corridor_type,
        age=age,
        area=area_pyeong,
        location_score=None,
    )


def perform_full_analysis(
    company_name: str,
    property_address: str,
    loan_amount: int,
    db: Optional[Session] = None,
) -> AnalysisResponse:
    """전체 분석 수행 - 실 수집 데이터 우선, 없으면 더미 폴백"""

    # 0. 실 수집 데이터 조회 시도
    real_data = None
    should_close_db = False

    if db is None:
        try:
            from core.database import SessionLocal
            db = SessionLocal()
            should_close_db = True
        except Exception as e:
            logger.warning(f"DB 연결 불가, 더미 데이터 사용: {e}")
            db = None

    if db is not None:
        try:
            real_data = get_real_market_data(db, property_address)
        except Exception as e:
            logger.warning(f"실 데이터 조회 실패, 더미 폴백: {e}")
            real_data = None
        finally:
            if should_close_db:
                db.close()

    # 담보 물건 기초 정보: 실 DB 우선, 없으면 더미
    if real_data and real_data.get("complex"):
        property_basic_info = _build_real_property_basic_info(
            real_data["complex"],
            real_data.get("area"),
            property_address,
        )
    else:
        property_basic_info = generate_property_basic_info(property_address)

    # 1. 더미 데이터 생성 (실 데이터 없는 항목만)
    borrower_info = generate_borrower_info(company_name)
    guarantor_info = generate_guarantor_info()
    property_rights_info = generate_property_rights_info()

    # 시세 데이터: 실 데이터 우선, 없으면 더미
    credit_data = (
        real_data["credit_data"]
        if real_data and real_data.get("credit_data")
        else generate_credit_data(property_address)
    )

    # 1-1. 입지 점수 생성 (항상 더미 - 지리 API 필요)
    location_scores = generate_location_scores(property_address)

    # 1-2. 인근 유사 물건지 동향: 실 데이터 우선
    nearby_trends = (
        real_data["nearby_trends"]
        if real_data and real_data.get("nearby_trends")
        else generate_nearby_property_trends(property_address, property_basic_info)
    )

    # 1-3. 평단가 추이: 실 데이터 우선
    price_per_pyeong = (
        real_data["price_per_pyeong"]
        if real_data and real_data.get("price_per_pyeong")
        else generate_price_per_pyeong_trend(
            property_address,
            credit_data.kb_price.estimated,
            property_basic_info.area or 34
        )
    )

    # 2. AI 종합 의견 생성 (하드코딩)
    # LTV 산출에 필요한 값
    total_prior = property_rights_info.max_bond_amount + property_rights_info.tenant_deposit + loan_amount
    ltv_current = round(total_prior / credit_data.kb_price.estimated * 100, 1) if credit_data.kb_price.estimated > 0 else 0
    ltv_jb = round(total_prior / credit_data.kb_price.low * 100, 1) if credit_data.kb_price.low > 0 else 0

    # 유사물건 평균 변동률
    avg_change = 0
    if nearby_trends.similar_properties:
        avg_change = round(
            sum(p.price_change_rate for p in nearby_trends.similar_properties)
            / len(nearby_trends.similar_properties) * 100, 1
        )

    # 평단가 추이 방향
    pyeong_data = price_per_pyeong.data
    pyeong_direction = "보합"
    if len(pyeong_data) >= 2:
        diff = pyeong_data[-1].complex - pyeong_data[0].complex
        if diff > 0:
            pyeong_direction = "상승"
        elif diff < 0:
            pyeong_direction = "하락"

    # TODO: Claude API 연동 시 아래 하드코딩 comprehensive_opinion을 삭제하고
    #       프롬프트 기반 API 호출로 교체
    # comprehensive_prompt = format_comprehensive_prompt(
    #     property_basic_info, property_rights_info, credit_data,
    #     nearby_trends, price_per_pyeong, loan_amount, ltv_current, ltv_jb
    # )
    # comprehensive_opinion = claude_client.analyze(comprehensive_prompt)
    # 가압류 존재 여부 확인 (갑구 기타사항에서)
    has_seizure = any(
        '가압류' in (e.get('purpose', '') if isinstance(e, dict) else getattr(e, 'purpose', ''))
        or '가처분' in (e.get('purpose', '') if isinstance(e, dict) else getattr(e, 'purpose', ''))
        for e in property_rights_info.ownership_other_entries
    )
    seizure_text = '가압류 1건 존재하여 해소 조건 부과 필요.' if has_seizure else '가압류 등 특이사항 없음.'

    comprehensive_opinion = f"""[입지] {property_address} 소재 물건은 역세권·학군·대단지 요건을 갖추고 있으며, 입지 종합 등급 A로 담보 적격성이 양호합니다.
[권리] 갑구 소유권 이전 이력 정상이며, 을구 선순위 근저당 {property_rights_info.max_bond_amount // 100000000}억원 설정 확인. {seizure_text}
[시세] KB 추정가 기준 최근 3개월 시세 흐름이 안정적이며, 국토부 실거래가·네이버 호가 모두 유사 수준으로 시세 신뢰도가 높습니다.
[유사물건] 반경 500m 내 유사 {len(nearby_trends.similar_properties)}개 단지의 최근 3개월 평균 변동률은 {avg_change:+.1f}%로, 인근 시세가 {'상승' if avg_change > 0 else '하락' if avg_change < 0 else '보합'} 추세입니다.
[평단가] 단지 평단가는 최근 3개월간 {pyeong_direction} 흐름이며, 읍면동·시군구 평균 대비 {'상회' if pyeong_data and pyeong_data[-1].complex > pyeong_data[-1].dong else '유사한 수준'}하고 있습니다.
[LTV] 선순위 채권 + 대출신청금액 합산 기준 현재 시세 LTV {ltv_current}%, JB 적정시세 LTV {ltv_jb}%로 {'사내 기준 이내로 대출 실행 가능합니다.' if ltv_jb <= 85 else '사내 기준 초과 가능성이 있어 한도 조정 검토가 필요합니다.'}"""

    # 3. AI 분석 (하드코딩)
    # TODO: Claude API 연동 시 아래 하드코딩 블록을 삭제하고 API 호출 블록으로 교체
    ai_analysis = AIAnalysis(
        comprehensive_opinion=comprehensive_opinion,

        property_analysis=f"""[AI 입지 분석 결과]

1. 교통 접근성 (역세권 / 업무지구)
  - 대상 물건: {property_address}
  - 역세권: 인근 지하철역 도보 7분 이내, 더블 역세권에 해당하여 대중교통 접근성 '우수'
  - GBD(강남권): 강남 업무지구까지 대중교통 약 20분 소요, 접근성 '양호'
  - CBD(도심권): 종로/광화문 도심 업무지구까지 약 35분 소요, 접근성 '보통'
  - YBD(여의도권): 여의도 업무지구까지 약 30분 소요, 접근성 '보통'

2. 학군 / 교육환경
  - 초품아: 단지 내 초등학교 배정 가능, 통학 도보 5분 이내
  - 학권가: 해당 지역은 학원가 밀집 지역으로 교육 수요 '매우 높음'
  - 중·고교 학군 선호도가 높아 실거주 수요가 견고한 지역

3. 단지 특성 (세대수 / 연식 / 브랜드)
  - 세대수: 약 4,400세대 대규모 단지로 커뮤니티 인프라 및 관리 여건 '우수'
  - 연식: 준공 후 약 15년 경과, 잔존 내용연수 충분 (리모델링 대상 가능)
  - 브랜드: 1군 건설사 시공 브랜드 아파트로 시장 선호도 '높음'
  - 커뮤니티시설: 피트니스, 독서실, 키즈카페, 게스트하우스 등 완비

4. 생활환경 / 자연환경
  - 마트: 대형마트(이마트/코스트코) 차량 5분 이내 접근 가능
  - 숲세권: 인근 근린공원 도보 10분 이내, 산책로 접근성 '양호'
  - 물세뷰: 한강 조망 가능 세대 존재, 리버뷰 프리미엄 형성 가능성 있음
  - 문화시설: 도서관, 복합문화센터, 영화관 등 도보/차량 10분 이내

5. 전세가율 분석
  - 현재 전세가율 약 62% 수준으로 실수요 기반의 안정적 시장 구조
  - 전세가율이 60% 이상으로 갭투자 수요보다 실거주 비중이 높은 것으로 판단

6. 종합 의견
  - 입지 종합 등급: '우수' (A등급)
  - 역세권 + 학군 + 대단지 + 브랜드의 복합 입지 프리미엄이 확인됩니다.
  - 담보물건으로서의 입지 적격성은 충분하며, 중장기 가치 유지 가능성이 높습니다.""",

        location_scores=location_scores,

        rights_analysis=RightsAnalysisDetail(
            gap_summary="등기부 갑구 확인 결과 현 소유자의 단독소유로 확인되며, 소유권 이전 이력은 정상적입니다. 가압류, 가처분 등 소유권 제한 사항은 존재하지 않습니다.",
            eul_summary="을구 확인 결과 근저당권 1건이 설정되어 있으며, 근질권(채권자: 제이비우리캐피탈)이 함께 설정되어 있습니다. 채권최고액 기준 선순위 부담을 고려한 담보 여력 산정이 필요합니다.",
            seizure_summary="갑구 및 을구에서 가압류, 가처분 등 권리 침해 사항은 확인되지 않습니다. 공적 제한 없이 담보 취득이 가능한 상태입니다.",
            priority_summary="현재 설정된 근저당권 기준 선순위 채권최고액을 고려하여 후순위 담보 취득 시 LTV 산정이 필요하며, 임차인 현황 확인을 통해 대항력 있는 임차권 존부를 추가 확인할 필요가 있습니다."
        ),

        market_analysis=f"""[AI 시세 분석 결과]

1. KB 시세 분석
  - KB 부동산 추정가 기준 해당 물건의 시세는 안정적인 흐름을 보이고 있습니다.
  - 최근 3개월간 소폭 상승 추세이며, 급격한 변동은 관찰되지 않습니다.

2. 실거래가 분석
  - 국토교통부 실거래가 데이터 기준 최근 거래는 KB 추정가 대비 유사한 수준에서 체결되었습니다.
  - 동일 단지 내 거래 빈도가 적정 수준으로, 유동성 리스크는 낮은 것으로 판단됩니다.

3. 매매호가 분석
  - 네이버 부동산 매매호가 기준 현재 호가는 KB 시세 대비 소폭 상회하고 있습니다.
  - 매물 수가 적정 범위로, 급매물 출현에 따른 가격 하락 리스크는 제한적입니다.

4. LTV 검토
  - 신청 금액 {loan_amount:,}원 기준 KB 추정가 대비 LTV 비율 산정이 필요합니다.
  - 사내 LTV 기준 충족 여부를 최종 확인한 후 대출 한도를 산정해야 합니다.

5. 종합 의견
  - 시세 안정성은 '양호'하며, 담보가치 대비 적정 대출 비율 내에서 대출 실행이 가능할 것으로 판단됩니다."""
    )

    # TODO: Claude API 연동 시 아래 블록 주석 해제
    # try:
    #     claude_client = ClaudeClient()
    #     property_prompt = format_property_prompt(property_basic_info, property_address)
    #     rights_prompt = format_rights_prompt(property_rights_info)
    #     market_prompt = format_market_prompt(credit_data, loan_amount)
    #     property_analysis = claude_client.analyze_property(property_prompt)
    #     rights_analysis = claude_client.analyze_rights(rights_prompt)
    #     market_analysis = claude_client.analyze_market(market_prompt)
    #     ai_analysis = AIAnalysis(
    #         property_analysis=property_analysis,
    #         rights_analysis=rights_analysis,
    #         market_analysis=market_analysis
    #     )
    # except Exception as e:
    #     ai_analysis = AIAnalysis(
    #         property_analysis=f"AI 분석을 수행할 수 없습니다: {str(e)}",
    #         rights_analysis=f"AI 분석을 수행할 수 없습니다: {str(e)}",
    #         market_analysis=f"AI 분석을 수행할 수 없습니다: {str(e)}"
    #     )

    # 3. 응답 생성
    analysis_data = AnalysisData(
        borrower_info=borrower_info,
        guarantor_info=guarantor_info,
        property_basic_info=property_basic_info,
        property_rights_info=property_rights_info,
        credit_data=credit_data,
        ai_analysis=ai_analysis,
        nearby_property_trends=nearby_trends,
        price_per_pyeong_trend=price_per_pyeong
    )

    return AnalysisResponse(
        status="success",
        data=analysis_data
    )
