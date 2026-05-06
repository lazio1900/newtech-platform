"""인증/인가 FastAPI Dependencies (ADR-004, ADR-005)."""
from typing import Iterable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import decode_access_token
from models import User, UserRole

# tokenUrl: OpenAPI 문서에서 토큰 발급 위치 안내. 실제 라우트는 main.py에 정의.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login", auto_error=False)


def _credentials_error(detail: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise _credentials_error("Not authenticated")
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise _credentials_error("Token expired")
    except jwt.InvalidTokenError:
        raise _credentials_error()

    user_id = payload.get("sub")
    if not user_id:
        raise _credentials_error()

    user: User | None = db.query(User).filter(User.user_id == user_id).first()
    if not user or not user.is_active:
        raise _credentials_error("User not found or inactive")
    return user


def require_role(*roles: UserRole | str):
    """라우트별 RBAC 가드. 예: `Depends(require_role(UserRole.AUDITOR, UserRole.ADMIN))`."""
    allowed = {r.value if isinstance(r, UserRole) else r for r in roles}

    def _checker(user: User = Depends(get_current_user)) -> User:
        user_role = user.role.value if isinstance(user.role, UserRole) else user.role
        if user_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_role}' not allowed (need: {sorted(allowed)})",
            )
        return user

    return _checker
