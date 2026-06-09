"""대출 신청 라우터: /api/applications/*"""
import logging
import re
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from core.auth import get_current_user, require_role
from core.database import SessionLocal, get_db
from models import (
    APPLICATION_STATUS_LABELS,
    ApplicationStatus,
    User,
    UserRole,
)
from services import application_service

logger = logging.getLogger(__name__)


def _prefetch_ai_analysis(application_id: str):
    """신청 등록 직후 백그라운드에서 LLM 입지/시세 분석 미리 생성 (캐시).

    auditor 가 신청건 분석 들어왔을 때 이미 캐시 히트되어 즉시 응답.
    실패해도 무방 — 호출 시점에 다시 시도됨.
    """
    from core.config import settings
    if settings.internal_only:
        # internal_only: 크롤 기반 prefetch 금지(AI 캐시 오염 차단). 호출 시점 perform_full_analysis
        # 가 CCTR_*/nice_rles_* 로 처리. (크롤 시세/실거래/매물/facility 읽기·캐시 write 모두 회피)
        return
    db = SessionLocal()
    try:
        from models.complex import Complex
        from models.loan import LoanApplication
        from services.ai_property_analysis_service import generate_or_get_cached as gen_property
        from services.ai_market_analysis_service import generate_or_get_cached as gen_market
        from services.location_score_service import compute_location_scores
        from services.real_data_service import (
            build_real_credit_data, build_real_nearby_trends, resolve_area
        )
        from models.complex import Area

        app = db.query(LoanApplication).filter(LoanApplication.id == application_id).first()
        if not app or not app.complex_id:
            return
        complex_obj = db.query(Complex).filter(Complex.id == app.complex_id).first()
        if not complex_obj:
            return

        # 데이터 준비 (DB 조회 + dataclass 산출) — 메인 세션
        scores = compute_location_scores(db, complex_obj)

        area_obj = None
        if app.area_id:
            area_obj = db.query(Area).filter(Area.id == app.area_id).first()
        if area_obj is None:
            area_obj = resolve_area(db, complex_obj.id, target_pyeong=app.pyeong)

        credit = nearby = ppp = None
        if area_obj is not None:
            credit = build_real_credit_data(db, complex_obj, area_obj)
            nearby = build_real_nearby_trends(db, complex_obj, area_obj)
            from services.real_data_service import build_real_price_per_pyeong
            ppp = build_real_price_per_pyeong(db, complex_obj, area_obj)

        # 병렬 실행용 스칼라 추출 (ORM 인스턴스를 스레드로 넘기지 않음)
        complex_id = complex_obj.id
        complex_name = complex_obj.name
        app_pyeong = app.pyeong
        app_loan_amount = app.loan_amount
        app_registry_ic_id = app.registry_ic_id
        app_rles_unq_no = app.rles_unq_no

        tasks = {}
        if scores is not None:
            def _property(local_db, _scores=scores, _pyeong=app_pyeong, _cid=complex_id):
                co = local_db.query(Complex).filter(Complex.id == _cid).first()
                return gen_property(
                    db=local_db, application_id=application_id,
                    complex_obj=co, scores=_scores, pyeong=_pyeong,
                )
            tasks["property"] = _property

        if credit is not None:
            def _market(local_db, _credit=credit, _nearby=nearby, _amt=app_loan_amount, _py=app_pyeong):
                return gen_market(
                    db=local_db, application_id=application_id,
                    credit=_credit, nearby=_nearby,
                    loan_amount=_amt, total_prior=_amt, pyeong=_py,
                )
            tasks["market"] = _market

        if nearby is not None and nearby.similar_properties:
            from services.ai_nearby_analysis_service import generate_or_get_cached as gen_nearby
            # 타겟 메타 — LLM 환각 방지차 prompt 에 명시 전달
            t_age = None
            if complex_obj.built_year:
                try:
                    t_age = date.today().year - int(str(complex_obj.built_year)[:4])
                except (ValueError, TypeError):
                    pass
            t_units = complex_obj.total_households

            def _nearby(local_db, _name=complex_name, _nb=nearby, _ppp=ppp,
                        _py=app_pyeong, _age=t_age, _units=t_units):
                return gen_nearby(
                    db=local_db, application_id=application_id,
                    target_complex_name=_name,
                    target_recent_price=_nb.target_recent_price,
                    nearby=_nb, ppp=_ppp,
                    target_pyeong=_py, target_age=_age, target_units=_units,
                )
            tasks["nearby"] = _nearby

        if app_registry_ic_id or app_rles_unq_no:
            from services.rights_source import get_rights_data
            def _rights(local_db, _ic=app_registry_ic_id, _unq=app_rles_unq_no):
                return get_rights_data(local_db, application_id, _ic, _unq)
            tasks["rights"] = _rights

        if tasks:
            from utils.parallel import run_with_session
            run_with_session(tasks)

        # 종합 의견 + 심사역 권고는 perform_full_analysis 의 마지막 단계에 호출됨.
        # prefetch 시점에 perform_full_analysis 통째로 한 번 돌리면 모든 분석 결과 종합 가능.
        try:
            from services.analysis_service import perform_full_analysis
            perform_full_analysis(
                company_name=app.company_name,
                property_address=app.property_address,
                loan_amount=app.loan_amount,
                db=db,
                target_pyeong=app.pyeong,
                complex_id=app.complex_id,
                area_id=app.area_id,
                complex_name=app.complex_name,
                application_id=application_id,
            )
        except Exception as e:
            logger.warning(f"[prefetch] overall opinion failed: {e}")

        logger.info(f"[prefetch_ai_analysis] cached for application {application_id}")
    except Exception as e:
        logger.warning(f"[prefetch_ai_analysis] failed for application {application_id}: {e}")
    finally:
        db.close()

router = APIRouter()


def _normalize_rles_unq_no(v: str | None) -> str | None:
    """부동산고유번호(RLES_UNQ_NO) 정규화 — 하이픈/공백 제거 후 14자리 숫자만 허용.

    입력 예 '1149-1996-233513' → 저장 '11491996233513'. 빈 값은 None.
    """
    if v is None:
        return None
    digits = re.sub(r"\D", "", v)
    if not digits:
        return None
    if len(digits) != 14:
        raise ValueError("부동산고유번호는 숫자 14자리여야 합니다.")
    return digits


class ApplicationCreateRequest(BaseModel):
    """신청자는 토큰의 사용자로 결정 (body의 applicant_id는 무시)."""
    company_name: str = Field(..., min_length=1, max_length=200)
    ceo_name: str = Field(..., min_length=1, max_length=80)
    business_number: str | None = Field(None, max_length=20, description="사업자등록번호 (audit 직접조회 케이스 등록 시 수기 입력)")
    credit_score_nice: int | None = Field(None, ge=0, le=1000, description="대표자 NICE 신용점수")
    credit_score_kcb: int | None = Field(None, ge=0, le=1000, description="대표자 KCB 신용점수")
    property_address: str = Field(..., min_length=1, max_length=500)
    loan_amount: int = Field(..., gt=0)
    loan_duration: int = Field(12, ge=1, le=600)

    # 단지/평형 매칭 (선택). 단지 검색 결과를 선택하지 않은 경우 None 허용.
    complex_id: int | None = None
    complex_name: str | None = Field(None, max_length=200)
    area_id: int | None = None
    exclusive_m2: float | None = None
    pyeong: int | None = Field(None, ge=1, le=300)
    dong: str | None = Field(None, max_length=40)
    ho: str | None = Field(None, max_length=40)
    # 신청 전 발급한 등기부등본 ic_id (선택)
    registry_ic_id: int | None = None
    # 부동산고유번호 (14자리, 하이픈 허용) — 폐쇄망 등기부 조인키, 심사자 수기 입력
    rles_unq_no: str | None = Field(None, max_length=20)

    @field_validator("rles_unq_no")
    @classmethod
    def _v_rles_unq_no(cls, v: str | None) -> str | None:
        return _normalize_rles_unq_no(v)


class ApplicationStatusUpdateRequest(BaseModel):
    status: ApplicationStatus
    memo: str | None = Field(None, max_length=2000)


class ApplicationUpdateRequest(BaseModel):
    """신청건 본문 수정 — ApplicationCreateRequest 와 동일 필드. status 는 별도 라우트."""
    company_name: str = Field(..., min_length=1, max_length=200)
    ceo_name: str = Field(..., min_length=1, max_length=80)
    business_number: str | None = Field(None, max_length=20)
    credit_score_nice: int | None = Field(None, ge=0, le=1000)
    credit_score_kcb: int | None = Field(None, ge=0, le=1000)
    property_address: str = Field(..., min_length=1, max_length=500)
    loan_amount: int = Field(..., gt=0)
    loan_duration: int = Field(12, ge=1, le=600)
    complex_id: int | None = None
    complex_name: str | None = Field(None, max_length=200)
    area_id: int | None = None
    exclusive_m2: float | None = None
    pyeong: int | None = Field(None, ge=1, le=300)
    dong: str | None = Field(None, max_length=40)
    ho: str | None = Field(None, max_length=40)
    registry_ic_id: int | None = None
    rles_unq_no: str | None = Field(None, max_length=20)

    @field_validator("rles_unq_no")
    @classmethod
    def _v_rles_unq_no(cls, v: str | None) -> str | None:
        return _normalize_rles_unq_no(v)


@router.post("")
def submit(
    request: ApplicationCreateRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    app = application_service.submit(
        db,
        applicant=user,
        company_name=request.company_name,
        ceo_name=request.ceo_name,
        business_number=request.business_number,
        credit_score_nice=request.credit_score_nice,
        credit_score_kcb=request.credit_score_kcb,
        property_address=request.property_address,
        loan_amount=request.loan_amount,
        loan_duration=request.loan_duration,
        complex_id=request.complex_id,
        complex_name=request.complex_name,
        area_id=request.area_id,
        exclusive_m2=request.exclusive_m2,
        pyeong=request.pyeong,
        dong=request.dong,
        ho=request.ho,
        registry_ic_id=request.registry_ic_id,
        rles_unq_no=request.rles_unq_no,
    )

    # 백그라운드로 LLM 입지 분석 미리 생성 — auditor 진입 시 캐시 히트
    if app.complex_id:
        background_tasks.add_task(_prefetch_ai_analysis, app.id)

    return {"status": "success", "application": app.to_dict()}


@router.get("")
def list_applications(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """customer는 자기 신청만, auditor/admin은 전체."""
    role_value = user.role.value if isinstance(user.role, UserRole) else user.role
    if role_value == UserRole.CUSTOMER.value:
        apps = application_service.list_for_applicant(db, user.id)
    else:
        apps = application_service.list_all(db)
    return [a.to_dict() for a in apps]


@router.get("/status-options")
def status_options():
    """상태 드롭다운 메타."""
    return [
        {"value": s.value, "label": APPLICATION_STATUS_LABELS[s]}
        for s in ApplicationStatus
    ]


@router.put("/{app_id}")
def update_application(
    app_id: str,
    request: ApplicationUpdateRequest,
    _: User = Depends(require_role(UserRole.AUDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """신청건 본문 수정. status / decided_at 은 별도 라우트로 변경."""
    result = application_service.update(
        db,
        app_id=app_id,
        company_name=request.company_name,
        ceo_name=request.ceo_name,
        business_number=request.business_number,
        credit_score_nice=request.credit_score_nice,
        credit_score_kcb=request.credit_score_kcb,
        property_address=request.property_address,
        loan_amount=request.loan_amount,
        loan_duration=request.loan_duration,
        complex_id=request.complex_id,
        complex_name=request.complex_name,
        area_id=request.area_id,
        exclusive_m2=request.exclusive_m2,
        pyeong=request.pyeong,
        dong=request.dong,
        ho=request.ho,
        registry_ic_id=request.registry_ic_id,
        rles_unq_no=request.rles_unq_no,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="신청건을 찾을 수 없습니다.")
    return {"status": "success", "application": result.to_dict()}


@router.put("/{app_id}/status")
def update_status(
    app_id: str,
    body: ApplicationStatusUpdateRequest,
    auditor: User = Depends(require_role(UserRole.AUDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    try:
        result = application_service.update_status(
            db,
            app_id=app_id,
            new_status=body.status,
            auditor=auditor,
            memo=body.memo,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="신청건을 찾을 수 없습니다.")
    return {"status": "success", "application": result.to_dict()}
