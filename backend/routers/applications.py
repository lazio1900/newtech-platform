"""대출 신청 라우터: /api/applications/*"""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
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

        # 입지 분석 prefetch
        scores = compute_location_scores(db, complex_obj)
        if scores is not None:
            gen_property(
                db=db, application_id=application_id,
                complex_obj=complex_obj, scores=scores, pyeong=app.pyeong,
            )

        # 시세 분석 prefetch
        area_obj = None
        if app.area_id:
            area_obj = db.query(Area).filter(Area.id == app.area_id).first()
        if area_obj is None:
            area_obj = resolve_area(db, complex_obj.id, target_pyeong=app.pyeong)
        if area_obj is not None:
            credit = build_real_credit_data(db, complex_obj, area_obj)
            nearby = build_real_nearby_trends(db, complex_obj, area_obj)
            from services.real_data_service import build_real_price_per_pyeong
            ppp = build_real_price_per_pyeong(db, complex_obj, area_obj)
            if credit is not None:
                gen_market(
                    db=db, application_id=application_id,
                    credit=credit, nearby=nearby,
                    loan_amount=app.loan_amount,
                    total_prior=app.loan_amount,
                    pyeong=app.pyeong,
                )
            # 유사물건 종합 코멘트 prefetch
            if nearby is not None and nearby.similar_properties:
                from services.ai_nearby_analysis_service import generate_or_get_cached as gen_nearby
                gen_nearby(
                    db=db, application_id=application_id,
                    target_complex_name=complex_obj.name,
                    target_recent_price=nearby.target_recent_price,
                    nearby=nearby, ppp=ppp,
                )

        # 등기부 LLM 권리 분석 prefetch (registry_ic_id 있을 때만)
        if app.registry_ic_id:
            from services.ai_rights_analysis_service import generate_or_get_cached as gen_rights
            gen_rights(db, application_id, app.registry_ic_id)

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


class ApplicationCreateRequest(BaseModel):
    """신청자는 토큰의 사용자로 결정 (body의 applicant_id는 무시)."""
    company_name: str = Field(..., min_length=1, max_length=200)
    ceo_name: str = Field(..., min_length=1, max_length=80)
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


class ApplicationStatusUpdateRequest(BaseModel):
    status: ApplicationStatus
    memo: str | None = Field(None, max_length=2000)


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
