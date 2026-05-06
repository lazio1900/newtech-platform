"""자동완성 라우터: /api/suggestions"""
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.database import get_db
from models import SearchField, User
from services import history_service

router = APIRouter()


@router.get("")
def suggestions(
    field: str = Query(..., description="검색 필드 (company 또는 address)"),
    query: str = Query(..., min_length=1, max_length=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[str]:
    try:
        field_enum = SearchField(field)
    except ValueError:
        return []
    return history_service.search(db, field=field_enum, query=query)
