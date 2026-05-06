"""FastAPI 진입점.

도메인 라우트는 routers/ 패키지로 분리. 본 파일은 앱 셋업, 미들웨어, startup 훅,
라우터 등록만 담당.
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import assert_production_safe, settings
from routers import (
    analyze,
    applications,
    auth,
    complexes,
    health,
    monitoring,
    regions,
    suggestions,
)

assert_production_safe()

logger = logging.getLogger(__name__)

# redirect_slashes=False — 308 redirect 시 Location URL 의 host:port 가 nginx 환경에서
# 깨지는 케이스 방지. 라우터 path 는 trailing slash 없이 일관 사용.
app = FastAPI(
    title="JB우리캐피탈 질권 담보 대출 업무 플랫폼 API",
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Routers
app.include_router(health.router,        prefix="/api/health",        tags=["health"])
app.include_router(auth.router,          prefix="/api",               tags=["auth"])
app.include_router(suggestions.router,   prefix="/api/suggestions",   tags=["suggestions"])
app.include_router(applications.router,  prefix="/api/applications",  tags=["applications"])
app.include_router(monitoring.router,    prefix="/api/monitoring",    tags=["monitoring"])
app.include_router(analyze.router,       prefix="/api/analyze",       tags=["analyze"])
app.include_router(complexes.router,     prefix="/api/complexes",     tags=["complexes"])
app.include_router(regions.router,       prefix="/api/regions",       tags=["regions"])


@app.on_event("startup")
def on_startup() -> None:
    """스키마는 Alembic으로 관리 (ADR-002). startup은 DB 연결 검증만."""
    try:
        from sqlalchemy import text
        from core.database import engine
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection OK")
    except Exception as e:
        logger.warning("Database connection check failed: %s", e)
