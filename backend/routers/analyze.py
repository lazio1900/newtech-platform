"""담보 분석 라우터: /api/analyze"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.database import get_db
from models import SearchField, User
from models.request_models import AnalysisRequest
from models.response_models import AnalysisResponse
from services import history_service
from services.analysis_service import perform_full_analysis

router = APIRouter()


@router.post("", response_model=AnalysisResponse)
def analyze(
    request: AnalysisRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """대출 담보 분석. 검색이력 자동 기록."""
    history_service.record(db, field=SearchField.COMPANY, value=request.company_name, user_id=user.id)
    history_service.record(db, field=SearchField.ADDRESS, value=request.property_address, user_id=user.id)

    return perform_full_analysis(
        company_name=request.company_name,
        property_address=request.property_address,
        loan_amount=request.loan_amount,
        db=db,
        target_pyeong=request.pyeong,
        complex_id=request.complex_id,
        area_id=request.area_id,
        complex_name=request.complex_name,
        application_id=request.application_id,
    )
