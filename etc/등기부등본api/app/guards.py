from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import RegistryRequest


class GuardError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def check_kill_switch() -> None:
    if not settings.REGISTRY_ENABLED:
        raise GuardError("disabled", "registry api is disabled")


def _count_paid_since(db: Session, since: datetime) -> int:
    q = select(func.count(RegistryRequest.id)).where(
        RegistryRequest.created_at >= since,
        RegistryRequest.cost > 0,
    )
    return db.execute(q).scalar() or 0


def check_rate_limits(db: Session) -> None:
    now = datetime.now(timezone.utc)
    daily = _count_paid_since(db, now - timedelta(days=1))
    if daily >= settings.DAILY_LIMIT:
        raise GuardError(
            "daily_limit",
            f"daily limit reached ({daily}/{settings.DAILY_LIMIT})",
        )
    hourly = _count_paid_since(db, now - timedelta(hours=1))
    if hourly >= settings.HOURLY_LIMIT:
        raise GuardError(
            "hourly_limit",
            f"hourly limit reached ({hourly}/{settings.HOURLY_LIMIT})",
        )


def find_recent_listing_request(
    db: Session, listing_id: Optional[str]
) -> Optional[RegistryRequest]:
    if not listing_id:
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.DUPLICATE_BLOCK_HOURS)
    q = (
        select(RegistryRequest)
        .where(
            RegistryRequest.listing_id == listing_id,
            RegistryRequest.created_at >= cutoff,
            RegistryRequest.status.in_(("issuing", "completed")),
        )
        .order_by(RegistryRequest.created_at.desc())
        .limit(1)
    )
    return db.execute(q).scalar_one_or_none()
