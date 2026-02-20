from fastapi import FastAPI, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from pydantic import BaseModel
from models.request_models import AnalysisRequest
from models.response_models import AnalysisResponse
from services.analysis_service import perform_full_analysis
from services.history_store import search_history
from services.auth_store import auth_store
from services.application_store import application_store
from services.monitoring_store import monitoring_store

app = FastAPI(title="JB우리캐피탈 질권 담보 대출 업무 플랫폼 API")

# CORS 미들웨어 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Newtech routers (각 라우터 독립적 임포트) ---
import importlib
import logging

_logger = logging.getLogger(__name__)

for _name, _module, _prefix, _tags in [
    ("complexes", "routers.complexes", "/api/complexes", ["complexes"]),
    ("jobs",      "routers.jobs",      "/api/jobs",      ["jobs"]),
    ("runs",      "routers.runs",      "/api/runs",      ["runs"]),
    ("data",      "routers.data_explorer", "/api/data",  ["data_explorer"]),
    ("batches",   "routers.batches",   "/api/batches",   ["batches"]),
]:
    try:
        _mod = importlib.import_module(_module)
        app.include_router(_mod.router, prefix=_prefix, tags=_tags)
    except Exception as _e:
        _logger.warning(f"Router '{_name}' load failed (skipped): {_e}")


# --- Database table creation on startup ---
@app.on_event("startup")
def on_startup():
    try:
        from core.database import engine
        from models import Base
        Base.metadata.create_all(bind=engine)

        # 기존 테이블에 새 컬럼 자동 추가 (create_all은 기존 테이블에 컬럼 추가 안함)
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        if "complexes" in inspector.get_table_names():
            existing = {c["name"] for c in inspector.get_columns("complexes")}
            migrations = [
                ("total_households", "INTEGER"),
                ("corridor_type", "VARCHAR(50)"),
                ("build_year", "INTEGER"),
            ]
            with engine.begin() as conn:
                for col_name, col_type in migrations:
                    if col_name not in existing:
                        conn.execute(text(
                            f"ALTER TABLE complexes ADD COLUMN {col_name} {col_type}"
                        ))
                        import logging
                        logging.getLogger(__name__).info(
                            f"Added column complexes.{col_name}"
                        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"Database table creation skipped (DB may not be available): {e}"
        )


@app.get("/api/health")
def health_check():
    """서버 상태 확인 엔드포인트"""
    return {
        "status": "ok",
        "message": "JB우리캐피탈 대출 분석 API 서버가 정상 작동 중입니다."
    }


@app.get("/api/suggestions")
def get_suggestions(
    field: str = Query(..., description="검색 필드 (company 또는 address)"),
    query: str = Query(..., description="검색어", min_length=1)
) -> List[str]:
    """자동완성 추천어 조회 엔드포인트"""
    if field == "company":
        return search_history.search_companies(query)
    elif field == "address":
        return search_history.search_addresses(query)
    else:
        return []


# === 인증 API ===

class LoginRequest(BaseModel):
    user_id: str
    password: str

class RegisterRequest(BaseModel):
    user_id: str
    password: str
    company_name: str
    ceo_name: str
    business_number: str
    phone: str

class ApplicationRequest(BaseModel):
    applicant_id: str
    company_name: str
    ceo_name: str
    property_address: str
    loan_amount: int
    loan_duration: int = 12


@app.post("/api/login")
def login(request: LoginRequest):
    """로그인"""
    user = auth_store.login(request.user_id, request.password)
    if not user:
        return {"status": "error", "message": "아이디 또는 비밀번호가 올바르지 않습니다."}
    return {
        "status": "success",
        "user": {
            "user_id": user.user_id,
            "role": user.role,
            "company_name": user.company_name,
            "ceo_name": user.ceo_name,
            "business_number": user.business_number,
            "phone": user.phone
        }
    }


@app.post("/api/register")
def register(request: RegisterRequest):
    """회원가입 (대부업체)"""
    user = auth_store.register(
        user_id=request.user_id,
        password=request.password,
        company_name=request.company_name,
        ceo_name=request.ceo_name,
        business_number=request.business_number,
        phone=request.phone
    )
    if not user:
        return {"status": "error", "message": "이미 존재하는 아이디입니다."}
    return {"status": "success", "message": "회원가입이 완료되었습니다."}


# === 신청 API ===

@app.post("/api/applications")
def submit_application(request: ApplicationRequest):
    """대출 신청 제출"""
    app_obj = application_store.submit(
        applicant_id=request.applicant_id,
        company_name=request.company_name,
        ceo_name=request.ceo_name,
        property_address=request.property_address,
        loan_amount=request.loan_amount,
        loan_duration=request.loan_duration
    )
    return {"status": "success", "application": app_obj.to_dict()}


@app.get("/api/applications")
def get_applications(applicant_id: str = None):
    """신청 목록 조회"""
    if applicant_id:
        return application_store.get_by_applicant(applicant_id)
    return application_store.get_all()


@app.put("/api/applications/{app_id}/status")
def update_application_status(app_id: str, status: str, memo: str = ""):
    """신청 상태 변경 (심사자)"""
    result = application_store.update_status(app_id, status, memo)
    if not result:
        return {"status": "error", "message": "신청건을 찾을 수 없습니다."}
    return {"status": "success", "application": result}


# === 모니터링 API ===

@app.get("/api/monitoring")
def get_monitoring_loans():
    """사후모니터링 대출 목록"""
    return {
        "loans": monitoring_store.get_all(),
        "summary": monitoring_store.get_summary()
    }


@app.get("/api/monitoring/{loan_id}")
def get_monitoring_detail(loan_id: str):
    """사후모니터링 대출 상세"""
    loan = monitoring_store.get_by_id(loan_id)
    if not loan:
        return {"status": "error", "message": "대출건을 찾을 수 없습니다."}
    return loan


class MonitoringRegisterRequest(BaseModel):
    auditor_name: str
    company_name: str
    ceo_name: str
    property_address: str
    loan_amount: int
    execution_price: int


@app.post("/api/monitoring")
def register_monitoring_loan(request: MonitoringRegisterRequest):
    """승인 대출을 사후모니터링에 등록"""
    loan = monitoring_store.add_loan(
        auditor_name=request.auditor_name,
        company_name=request.company_name,
        ceo_name=request.ceo_name,
        property_address=request.property_address,
        loan_amount=request.loan_amount,
        execution_price=request.execution_price
    )
    return {"status": "success", "loan": loan}


# === 분석 API ===

def _get_db_optional():
    """분석용 DB 세션 (DB 미연결 시에도 동작하도록 Optional)"""
    try:
        from core.database import get_db
        db = next(get_db())
        try:
            yield db
        finally:
            db.close()
    except Exception:
        yield None


@app.post("/api/analyze", response_model=AnalysisResponse)
def analyze_property(request: AnalysisRequest, db=Depends(_get_db_optional)):
    """대출 담보 분석 엔드포인트"""
    search_history.add_company(request.company_name)
    search_history.add_address(request.property_address)

    return perform_full_analysis(
        company_name=request.company_name,
        property_address=request.property_address,
        loan_amount=request.loan_amount,
        db=db,
    )
