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

# TODO: Phase 3에서 LLM 실연동. 활성화 시 아래 주석 해제 (ADR-008).
# from services.llm_service import LLMClient
# from utils.prompts import (
#     format_property_prompt,
#     format_rights_prompt,
#     format_market_prompt
# )


def _build_real_property_basic_info(
    complex_obj,
    area_obj,
    property_address: str,
    location_scores=None,
) -> PropertyBasicInfo:
    """DB의 Complex/Area 데이터로 담보 물건 기초 정보를 구성한다.

    location_scores 가 주어지면 6개 카테고리 평균을 location_score 에 채운다.
    """
    units = complex_obj.total_households
    corridor_type = complex_obj.hallway_type

    age = None
    if complex_obj.built_year:
        try:
            age = date.today().year - int(str(complex_obj.built_year)[:4])
        except (ValueError, TypeError):
            age = None

    area_pyeong = None
    if area_obj:
        if area_obj.pyeong:
            area_pyeong = int(area_obj.pyeong)
        elif area_obj.exclusive_m2:
            area_pyeong = int(area_obj.exclusive_m2 / 3.305785)

    # 단일 location_score = LocationScores 6개 카테고리 평균 (없으면 N/A)
    location_score = None
    if location_scores is not None:
        location_score = round(
            (location_scores.station_walk + location_scores.commute_time
             + location_scores.school_walk + location_scores.units_score
             + location_scores.living_env + location_scores.nature_env) / 6
        )

    return PropertyBasicInfo(
        complex_name=complex_obj.name,
        address=property_address or complex_obj.address,
        units=units,
        corridor_type=corridor_type,
        age=age,
        area=area_pyeong,
        exclusive_m2=area_obj.exclusive_m2 if area_obj else None,
        supply_m2=area_obj.supply_m2 if area_obj else None,
        location_score=location_score,
    )


def perform_full_analysis(
    company_name: str,
    property_address: str,
    loan_amount: int,
    db: Optional[Session] = None,
    target_pyeong: Optional[int] = None,
    complex_id: Optional[int] = None,
    area_id: Optional[int] = None,
    complex_name: Optional[str] = None,
    application_id: Optional[str] = None,
) -> AnalysisResponse:
    """전체 분석 수행 - 실 수집 데이터 우선, 없으면 더미 폴백.

    complex_id/area_id 가 주어지면 fuzzy 매칭 대신 직접 조회 (정확함).
    complex_name 은 dummy 폴백 시 단지명 표시에 사용.
    """

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
            real_data = get_real_market_data(
                db,
                property_address,
                target_pyeong=target_pyeong,
                complex_id=complex_id,
                area_id=area_id,
            )
        except Exception as e:
            logger.warning(f"실 데이터 조회 실패, 더미 폴백: {e}")
            real_data = None

    # 1. 더미 데이터 생성 (실 데이터 없는 항목만)
    borrower_info = generate_borrower_info(company_name)
    guarantor_info = generate_guarantor_info()
    property_rights_info = generate_property_rights_info(property_address)

    # 1-0. 등기부등본 LLM 권리 분석 — 신청건에 registry_ic_id 가 있으면 PDF 추출 + LLM
    rights_llm: dict = {}
    registry_ic_id_for_app = None
    if application_id and db is not None:
        try:
            from models.loan import LoanApplication
            la = db.query(LoanApplication).filter(LoanApplication.id == application_id).first()
            if la and la.registry_ic_id:
                registry_ic_id_for_app = la.registry_ic_id
                from services.ai_rights_analysis_service import generate_or_get_cached as gen_rights
                rights_llm = gen_rights(db, application_id, la.registry_ic_id)
        except Exception as e:
            logger.warning(f"AI 권리 분석 실패: {e}")
    # rights_llm 결과로 property_rights_info 의 표 4종 + 합계 채움 (있으면)
    # 등기부 추출이 한 건이라도 성공하면 합계도 항상 덮어쓰기 (0 도 의미있는 실값)
    if rights_llm.get("ownership_entries") or rights_llm.get("mortgage_entries"):
        property_rights_info.ownership_entries = rights_llm.get("ownership_entries") or []
        property_rights_info.ownership_other_entries = rights_llm.get("ownership_other_entries") or []
        property_rights_info.mortgage_entries = rights_llm.get("mortgage_entries") or []
        property_rights_info.max_bond_amount = int(rights_llm.get("max_bond_amount") or 0)
        property_rights_info.tenant_deposit = int(rights_llm.get("tenant_deposit") or 0)

    # 시세 데이터: 실 데이터 우선, 없으면 더미
    credit_data = (
        real_data["credit_data"]
        if real_data and real_data.get("credit_data")
        else generate_credit_data(property_address)
    )

    # 1-1. 입지 점수: 실 facility 데이터(학군/지하철/병원/공원) 우선, 없으면 더미
    location_scores = None
    if real_data and real_data.get("complex") and db is not None:
        try:
            from services.location_score_service import compute_location_scores
            location_scores = compute_location_scores(db, real_data["complex"])
        except Exception as e:
            logger.warning(f"입지점수 산출 실패, 더미 폴백: {e}")
    if location_scores is None:
        location_scores = generate_location_scores(property_address)

    # 담보 물건 기초 정보: 실 DB 우선, 없으면 더미.
    # location_scores 평균을 단일 location_score 에 주입 (N/A 방지).
    if real_data and real_data.get("complex"):
        property_basic_info = _build_real_property_basic_info(
            real_data["complex"],
            real_data.get("area"),
            property_address,
            location_scores=location_scores,
        )
    else:
        property_basic_info = generate_property_basic_info(
            property_address,
            complex_name=complex_name,
            pyeong=target_pyeong,
        )

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
    # JB 적정시세 기준 LTV (KB×0.3 + 실거래×0.6 + 호가×0.1)
    jb_basis = credit_data.jb_fair_price or credit_data.kb_price.low or credit_data.kb_price.estimated
    ltv_jb = round(total_prior / jb_basis * 100, 1) if jb_basis > 0 else 0

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

    # TODO: LLM API 연동 시 아래 하드코딩 comprehensive_opinion을 삭제하고
    #       프롬프트 기반 API 호출로 교체
    # comprehensive_prompt = format_comprehensive_prompt(
    #     property_basic_info, property_rights_info, credit_data,
    #     nearby_trends, price_per_pyeong, loan_amount, ltv_current, ltv_jb
    # )
    # comprehensive_opinion = llm_client.analyze(comprehensive_prompt)
    # 가압류 존재 여부 확인 (갑구 기타사항에서)
    has_seizure = any(
        '가압류' in (e.get('purpose', '') if isinstance(e, dict) else getattr(e, 'purpose', ''))
        or '가처분' in (e.get('purpose', '') if isinstance(e, dict) else getattr(e, 'purpose', ''))
        for e in property_rights_info.ownership_other_entries
    )
    seizure_text = '가압류 1건 존재하여 해소 조건 부과 필요.' if has_seizure else '가압류 등 특이사항 없음.'

    comprehensive_opinion_fallback = (
        f"[입지] 입지 데이터 분석 진행 중입니다.\n"
        f"[권리] 갑구·을구 확인 결과 선순위 근저당 {property_rights_info.max_bond_amount // 100000000}억원 설정. {seizure_text}\n"
        f"[시세] 최근 시세 흐름 분석 중입니다.\n"
        f"[유사물건] 인근 평균 변동률 {avg_change:+.1f}%.\n"
        f"[평단가] 단지 평단가 {pyeong_direction} 흐름.\n"
        f"[LTV] 현재 LTV {ltv_current}%, JB LTV {ltv_jb}%."
    )

    # 3. AI 입지 분석 — 실 facility 데이터 있으면 LLM, 없으면 더미
    property_analysis_text = None
    if real_data and real_data.get("complex") and db is not None:
        try:
            from services.ai_property_analysis_service import generate_or_get_cached
            property_analysis_text = generate_or_get_cached(
                db=db,
                application_id=application_id,
                complex_obj=real_data["complex"],
                scores=location_scores,
                pyeong=target_pyeong,
            )
        except Exception as e:
            logger.warning(f"AI 입지 분석 호출 실패, 더미 폴백: {e}")
    if not property_analysis_text:
        property_analysis_text = (
            f"[입지 분석] {property_address} 단지에 대해 현재 자동 분석 결과를 생성할 수 없습니다. "
            "단지 좌표와 주변 시설 데이터(학군/지하철/병원/공원)가 수집된 후 다시 시도해주세요."
        )

    # 3-2. AI 시세 분석 — 실 시세 데이터 있으면 LLM, 없으면 더미
    market_analysis_text = None
    if real_data and real_data.get("credit_data") and db is not None:
        try:
            from services.ai_market_analysis_service import generate_or_get_cached as gen_market
            market_analysis_text = gen_market(
                db=db,
                application_id=application_id,
                credit=credit_data,
                nearby=nearby_trends,
                loan_amount=loan_amount,
                total_prior=total_prior,
                pyeong=target_pyeong,
            )
        except Exception as e:
            logger.warning(f"AI 시세 분석 호출 실패, 더미 폴백: {e}")

    # 3-3. AI 유사물건 종합 코멘트 — 인근 + 평단가 통합
    nearby_analysis_text = None
    if real_data and nearby_trends and nearby_trends.similar_properties and db is not None:
        try:
            from services.ai_nearby_analysis_service import generate_or_get_cached as gen_nearby
            target_recent_price = nearby_trends.target_recent_price
            target_name = real_data["complex"].name if real_data.get("complex") else (complex_name or "")
            nearby_analysis_text = gen_nearby(
                db=db,
                application_id=application_id,
                target_complex_name=target_name,
                target_recent_price=target_recent_price,
                nearby=nearby_trends,
                ppp=price_per_pyeong,
            )
        except Exception as e:
            logger.warning(f"AI 유사물건 분석 호출 실패: {e}")

    # 3-4. AI 종합 의견 + 심사역 권고 — 모든 분석 사실 종합 LLM
    overall_opinion = comprehensive_opinion_fallback
    auditor_recommendation = ""
    if real_data and db is not None:
        try:
            from services.ai_overall_analysis_service import generate_or_get_cached as gen_overall
            ov = gen_overall(
                db=db, application_id=application_id,
                pbi=property_basic_info, scores=location_scores,
                credit=credit_data, nearby=nearby_trends, ppp=price_per_pyeong,
                rights=property_rights_info,
                loan_amount=loan_amount,
                ltv_current=ltv_current, ltv_jb=ltv_jb,
            )
            if ov.get("comprehensive_opinion"):
                overall_opinion = ov["comprehensive_opinion"]
            auditor_recommendation = ov.get("auditor_recommendation", "")
        except Exception as e:
            logger.warning(f"AI 종합 의견 호출 실패: {e}")

    ai_analysis = AIAnalysis(
        comprehensive_opinion=overall_opinion,
        auditor_recommendation=auditor_recommendation,

        property_analysis=property_analysis_text,
        nearby_analysis=nearby_analysis_text,

        location_scores=location_scores,

        rights_analysis=RightsAnalysisDetail(
            gap_summary=rights_llm.get("gap_summary") or "등기부 갑구 확인 결과 현 소유자의 단독소유로 확인되며, 소유권 이전 이력은 정상적입니다. 가압류, 가처분 등 소유권 제한 사항은 존재하지 않습니다.",
            eul_summary=rights_llm.get("eul_summary") or "을구 확인 결과 근저당권 1건이 설정되어 있으며, 근질권(채권자: 제이비우리캐피탈)이 함께 설정되어 있습니다. 채권최고액 기준 선순위 부담을 고려한 담보 여력 산정이 필요합니다.",
            seizure_summary=rights_llm.get("seizure_summary") or "갑구 및 을구에서 가압류, 가처분 등 권리 침해 사항은 확인되지 않습니다. 공적 제한 없이 담보 취득이 가능한 상태입니다.",
            priority_summary=rights_llm.get("priority_summary") or "현재 설정된 근저당권 기준 선순위 채권최고액을 고려하여 후순위 담보 취득 시 LTV 산정이 필요하며, 임차인 현황 확인을 통해 대항력 있는 임차권 존부를 추가 확인할 필요가 있습니다."
        ),

        market_analysis=market_analysis_text or (
            f"[종합 의견] AI 시세 분석 일시 사용 불가. KB 추정가 {credit_data.kb_price.estimated:,}원, "
            f"신청금액 {loan_amount:,}원 기준 LTV 산정이 필요합니다."
        ),
    )

    # TODO: LLM API 연동 시 아래 블록 주석 해제
    # try:
    #     llm_client = LLMClient()
    #     property_prompt = format_property_prompt(property_basic_info, property_address)
    #     rights_prompt = format_rights_prompt(property_rights_info)
    #     market_prompt = format_market_prompt(credit_data, loan_amount)
    #     property_analysis = llm_client.analyze_property(property_prompt)
    #     rights_analysis = llm_client.analyze_rights(rights_prompt)
    #     market_analysis = llm_client.analyze_market(market_prompt)
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

    if should_close_db and db is not None:
        db.close()

    return AnalysisResponse(
        status="success",
        data=analysis_data
    )
