from fastapi import Header, HTTPException, status

from .config import settings


def require_internal_token(x_internal_token: str = Header(default=None, alias="X-Internal-Token")):
    if not x_internal_token or x_internal_token != settings.INTERNAL_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid internal token",
        )
