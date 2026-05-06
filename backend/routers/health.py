"""헬스 체크 라우터.

Phase 5에서 /ready (DB/Redis 의존성 검사) 추가 예정.
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("")
def health():
    """간단한 liveness 체크."""
    return {"status": "ok"}
