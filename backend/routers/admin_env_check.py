"""환경 연동 점검 라우터: /api/admin/env-check.

GET  ""             — effective OIDC 설정 기반 config echo + probe
POST "/verify-token" — effective OIDC 설정으로 토큰 검증
GET  "/config"       — 저장된 OIDC 설정 조회 (source 표기)
PUT  "/config"       — OIDC 설정 DB 저장 (부분 갱신 허용)
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth import require_role
from core.config import settings
from core.database import get_db
from models import User, UserRole
from services import env_check_service, oidc_config_service

router = APIRouter()


class VerifyTokenRequest(BaseModel):
    token: str


class OidcConfigUpdate(BaseModel):
    issuer: Optional[str] = None
    realm: Optional[str] = None
    client_id: Optional[str] = None
    jwks_url: Optional[str] = None
    employee_claim: Optional[str] = None
    roles_claim: Optional[str] = None


@router.get("")
def get_env_check(
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """effective OIDC 설정 기반 config echo + Keycloak/정보계 적재 probe."""
    effective = oidc_config_service.get_effective(db, settings)
    items = [
        *env_check_service.check_keycloak(effective),
        env_check_service.check_internal_tables(db),
    ]
    all_ok = all(it["ok"] for it in items)
    return {
        "status": "success",
        "environment": settings.environment,
        "config": env_check_service.build_config_echo(settings, effective),
        "items": items,
        "all_ok": all_ok,
    }


@router.post("/verify-token")
def post_verify_token(
    body: VerifyTokenRequest,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """붙여넣은 토큰을 effective OIDC 설정으로 검증하고 사번/email/역할 클레임을 추출한다."""
    effective = oidc_config_service.get_effective(db, settings)
    return env_check_service.verify_token(effective, body.token)


@router.get("/config")
def get_oidc_config(
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """저장된 OIDC 설정 + source 반환."""
    effective = oidc_config_service.get_effective(db, settings)
    return effective


@router.put("/config")
def put_oidc_config(
    payload: OidcConfigUpdate,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """OIDC 설정을 DB에 저장. 부분 갱신 허용(None 필드는 무시)."""
    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    oidc_config_service.upsert(db, **fields)
    effective = oidc_config_service.get_effective(db, settings)
    return {"status": "success", "config": effective}
