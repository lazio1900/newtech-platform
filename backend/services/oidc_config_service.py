"""OIDC 설정 단일행 DB 저장·조회·effective 계산."""
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from core.config import Settings
from models.oidc_config import OidcConfig


def ensure_table(engine: Engine) -> None:
    OidcConfig.__table__.create(bind=engine, checkfirst=True)


def get_row(db: Session) -> OidcConfig | None:
    return db.query(OidcConfig).filter(OidcConfig.is_active == True).first()  # noqa: E712


def upsert(db: Session, **fields) -> OidcConfig:
    row = db.query(OidcConfig).first()
    if row is None:
        row = OidcConfig()
        db.add(row)
    for k, v in fields.items():
        if hasattr(row, k):
            setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


def get_effective(db: Session, settings: Settings) -> dict:
    """필드별 DB행 non-empty > settings(env) > 기본값. source 표기."""
    row = get_row(db)

    def pick(db_val: str, env_val: str, default: str = "") -> tuple[str, str]:
        if db_val and db_val.strip():
            return db_val, "db"
        if env_val and env_val.strip():
            return env_val, "env"
        return default, "default"

    issuer, s_issuer = pick(row.issuer if row else "", settings.keycloak_issuer)
    realm, s_realm = pick(row.realm if row else "", settings.keycloak_realm)
    client_id, s_client_id = pick(row.client_id if row else "", settings.keycloak_client_id)
    jwks_url, s_jwks = pick(row.jwks_url if row else "", settings.keycloak_jwks_url)
    employee_claim, _ = pick(
        row.employee_claim if row else "",
        settings.oidc_employee_claim,
        "employee_number",
    )
    roles_claim, _ = pick(
        row.roles_claim if row else "",
        settings.oidc_roles_claim,
        "realm_access.roles",
    )

    if not jwks_url and issuer:
        jwks_url = issuer.rstrip("/") + "/protocol/openid-connect/certs"

    sources = [s_issuer, s_realm, s_client_id, s_jwks]
    if "db" in sources:
        source = "db"
    elif "env" in sources:
        source = "env"
    else:
        source = "default"

    return {
        "issuer": issuer,
        "realm": realm,
        "client_id": client_id,
        "jwks_url": jwks_url,
        "employee_claim": employee_claim,
        "roles_claim": roles_claim,
        "source": source,
    }
