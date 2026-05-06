"""검색 자동완성 이력 서비스 (DB 기반)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import case, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from models import SearchField, SearchHistory


def record(
    db: Session,
    *,
    field: SearchField,
    value: str,
    user_id: Optional[int] = None,
) -> None:
    """UPSERT: 동일 (field, value) 존재 시 count+1, last_searched_at 갱신."""
    if not value or not value.strip():
        return
    value = value.strip()

    stmt = pg_insert(SearchHistory).values(
        field=field,
        value=value,
        user_id=user_id,
        count=1,
        last_searched_at=datetime.utcnow(),
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_search_history_field_value",
        set_={
            "count": SearchHistory.__table__.c.count + 1,
            "last_searched_at": datetime.utcnow(),
        },
    )
    db.execute(stmt)
    db.commit()


def search(db: Session, *, field: SearchField, query: str, limit: int = 10) -> list[str]:
    """필드별 부분일치 검색.

    정렬: 시작 일치 우선 → 길이 짧은 순 → 호출 빈도(count desc) → 사전순.
    """
    if not query or not query.strip():
        return []
    q = query.strip()

    starts_with = case((SearchHistory.value.ilike(f"{q}%"), 0), else_=1)

    rows = (
        db.query(SearchHistory.value)
        .filter(SearchHistory.field == field)
        .filter(SearchHistory.value.ilike(f"%{q}%"))
        .order_by(
            starts_with.asc(),
            func.length(SearchHistory.value).asc(),
            SearchHistory.count.desc(),
            SearchHistory.value.asc(),
        )
        .limit(limit)
        .all()
    )
    return [r[0] for r in rows]
