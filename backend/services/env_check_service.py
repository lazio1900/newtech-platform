"""환경 연동 점검: 같은 코드로 개인PC→클라우드→내부망을 probe 만 한다.

모든 값은 settings(.env)에서 읽고, 화면은 그 환경이 가리키는 곳만 확인한다.
소스 수정 없이 환경 전환은 .env 교체로만 이뤄진다. Keycloak 미설정(개인PC)은
오류가 아니라 '미설정' 상태로 표시한다.
"""
import httpx
import jwt
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.config import Settings

_HTTP_TIMEOUT = 5.0


def _mask_db_url(url: str) -> str:
    """`@` 앞 자격증명(user:password)을 가린다. 호스트/포트/DB 는 남긴다."""
    if "@" not in url:
        return url
    head, _, tail = url.partition("://")
    if not _:
        creds, _, rest = url.partition("@")
        return "***@" + rest
    creds_host, _, after = tail.partition("@")
    if not _:
        return url
    return f"{head}://***@{after}"


def build_config_echo(settings: Settings, effective: dict) -> list[dict]:
    """현재 환경이 가리키는 설정값을 그대로 보여준다(자격증명 마스킹)."""

    def v(value) -> str:
        if value is None or value == "":
            return "(미설정)"
        return str(value)

    return [
        {"label": "ENVIRONMENT", "value": v(settings.environment)},
        {"label": "DATA_MODE", "value": v(settings.data_mode)},
        {"label": "INTERNAL_ONLY", "value": v(settings.internal_only)},
        {"label": "REGISTRY_SOURCE", "value": v(settings.registry_source)},
        {"label": "DATABASE_URL", "value": _mask_db_url(settings.database_url)},
        {"label": "KEYCLOAK_ISSUER", "value": v(effective["issuer"])},
        {"label": "KEYCLOAK_REALM", "value": v(effective["realm"])},
        {"label": "KEYCLOAK_CLIENT_ID", "value": v(effective["client_id"])},
    ]


def check_keycloak(effective: dict) -> list[dict]:
    """issuer 가 가리키는 Keycloak 의 discovery + JWKS 도달성만 probe."""
    issuer = effective["issuer"]
    if not issuer:
        return [
            {
                "key": "keycloak",
                "label": "Keycloak",
                "ok": False,
                "detail": "issuer 미설정 (.env KEYCLOAK_ISSUER). 폐쇄망 운영 시 주입.",
                "link": None,
            }
        ]

    items: list[dict] = []
    discovery_url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    jwks_uri = effective["jwks_url"] or issuer.rstrip("/") + "/protocol/openid-connect/certs"
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            resp = client.get(discovery_url)
            resp.raise_for_status()
            doc = resp.json()
        if not effective["jwks_url"] and doc.get("jwks_uri"):
            jwks_uri = doc["jwks_uri"]
        items.append(
            {
                "key": "keycloak_discovery",
                "label": "Keycloak Discovery",
                "ok": True,
                "detail": f"{discovery_url} 도달. issuer={doc.get('issuer', '?')}",
                "link": None,
            }
        )
    except Exception as e:
        items.append(
            {
                "key": "keycloak_discovery",
                "label": "Keycloak Discovery",
                "ok": False,
                "detail": f"도달 실패: {type(e).__name__}: {str(e)[:200]}",
                "link": None,
            }
        )
        return items

    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            resp = client.get(jwks_uri)
            resp.raise_for_status()
            keys = resp.json().get("keys", [])
        items.append(
            {
                "key": "keycloak_jwks",
                "label": "Keycloak JWKS",
                "ok": True,
                "detail": f"JWKS 키 {len(keys)}개 ({jwks_uri})",
                "link": None,
            }
        )
    except Exception as e:
        items.append(
            {
                "key": "keycloak_jwks",
                "label": "Keycloak JWKS",
                "ok": False,
                "detail": f"JWKS 도달 실패: {type(e).__name__}: {str(e)[:200]}",
                "link": None,
            }
        )

    return items


def check_internal_tables(db: Session) -> dict:
    """정보계 적재 확인 — octr_loan_m / opdm_rles_gd_d 행수."""
    from core.config import settings

    def _count(table: str) -> int:
        try:
            return db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0
        except Exception:
            return 0

    loans = _count("octr_loan_m")
    goods = _count("opdm_rles_gd_d")
    detail = f"octr_loan_m={loans}행, opdm_rles_gd_d={goods}행"
    ok = True
    if settings.internal_only and (loans == 0 or goods == 0):
        ok = False
        detail += " — INTERNAL_ONLY=true 인데 정보계 적재 없음 (수집기 ETL 미수행)"
    return {
        "key": "internal_tables",
        "label": "정보계 적재",
        "ok": ok,
        "detail": detail,
        "link": None,
    }


def _dig_claim(payload: dict, dotted_path: str):
    """점표기 경로로 중첩 클레임 탐색. 예: realm_access.roles."""
    node = payload
    for part in dotted_path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def verify_token(effective: dict, token: str) -> dict:
    """JWKS RS256 서명검증 시도. cryptography+issuer 있으면 실검증, 아니면 unverified decode."""
    issues: list[str] = []
    verified = False
    payload: dict | None = None

    issuer = effective["issuer"]
    client_id = effective["client_id"]
    jwks_url = effective["jwks_url"]
    employee_claim = effective["employee_claim"]
    roles_claim = effective["roles_claim"]

    can_verify = bool(issuer)
    if can_verify:
        try:
            import cryptography  # noqa: F401
        except ImportError:
            can_verify = False
            issues.append("cryptography 미설치 — 서명검증 불가, unverified decode 로 진행")

    if can_verify:
        try:
            jwks_uri = jwks_url or issuer.rstrip("/") + "/protocol/openid-connect/certs"
            jwk_client = jwt.PyJWKClient(jwks_uri)
            signing_key = jwk_client.get_signing_key_from_jwt(token)
            decode_kwargs = {"algorithms": ["RS256"], "issuer": issuer}
            if client_id:
                decode_kwargs["audience"] = client_id
            else:
                decode_kwargs["options"] = {"verify_aud": False}
            payload = jwt.decode(token, signing_key.key, **decode_kwargs)
            verified = True
        except Exception as e:
            issues.append(f"서명검증 실패: {type(e).__name__}: {str(e)[:200]}")
    else:
        if not issuer:
            issues.append("issuer 미설정 — unverified decode")

    if payload is None:
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
        except Exception as e:
            return {
                "valid": False,
                "verified": False,
                "claims": {"employee_number": None, "email": None, "roles": []},
                "issues": issues + [f"토큰 디코드 실패: {type(e).__name__}: {str(e)[:200]}"],
                "detail": "토큰을 파싱할 수 없습니다.",
            }

    employee_number = payload.get(employee_claim)
    if employee_number is None:
        issues.append(f"사번 클레임 없음 ({employee_claim})")
    email = payload.get("email")
    if email is None:
        issues.append("email 클레임 없음")
    roles = _dig_claim(payload, roles_claim)
    if not isinstance(roles, list):
        if roles is not None:
            issues.append(f"역할 클레임이 리스트가 아님 ({roles_claim})")
        roles = []

    detail = "서명검증 통과" if verified else "서명 미검증 (페이로드만 추출)"
    return {
        "valid": True,
        "verified": verified,
        "claims": {
            "employee_number": str(employee_number) if employee_number is not None else None,
            "email": str(email) if email is not None else None,
            "roles": [str(r) for r in roles],
        },
        "issues": issues,
        "detail": detail,
    }
