import os
import re
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .apick import ApickClient, ApickError
from .config import settings
from .db import SessionLocal
from .guards import (
    GuardError,
    check_kill_switch,
    check_rate_limits,
    find_recent_listing_request,
)
from .models import RegistryRequest

_whitespace = re.compile(r"\s+")


def normalize_address(address: str, dong: Optional[str], ho: Optional[str]) -> str:
    parts = [address.strip()]
    if dong:
        parts.append(f"{dong.strip()}동")
    if ho:
        parts.append(f"{ho.strip()}호")
    return _whitespace.sub(" ", " ".join(parts)).strip()


def _find_today_cache(
    db: Session, address_norm: str, type_: str
) -> Optional[RegistryRequest]:
    q = (
        select(RegistryRequest)
        .where(
            RegistryRequest.address_norm == address_norm,
            RegistryRequest.type == type_,
            RegistryRequest.issued_date == date.today(),
            RegistryRequest.status.in_(("issuing", "completed")),
        )
        .order_by(RegistryRequest.id.desc())
        .limit(1)
    )
    return db.execute(q).scalar_one_or_none()


def issue_or_get(
    db: Session,
    *,
    address: str,
    dong: Optional[str],
    ho: Optional[str],
    type_: str,
    requester_id: Optional[str],
    listing_id: Optional[str],
    force_refresh: bool,
) -> RegistryRequest:
    check_kill_switch()

    if not force_refresh:
        recent = find_recent_listing_request(db, listing_id)
        if recent:
            return recent

    address_norm = normalize_address(address, dong, ho)

    cached = _find_today_cache(db, address_norm, type_)
    if cached and not force_refresh:
        return cached

    check_rate_limits(db)

    row = RegistryRequest(
        address=address,
        dong=dong,
        ho=ho,
        type=type_,
        address_norm=address_norm,
        issued_date=date.today(),
        status="requested",
        requester_id=requester_id,
        listing_id=listing_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    client = ApickClient()
    search_address = normalize_address(address, dong, ho)
    try:
        body = client.request_iros(search_address, type_)
    except ApickError as e:
        row.status = "failed"
        row.error_message = str(e)[:1000]
        db.commit()
        return row

    api = body.get("api", {}) or {}
    data = body.get("data", {}) or {}

    row.cost = int(api.get("cost", 0) or 0)
    row.apick_pl_id = api.get("pl_id")
    ic_id = data.get("ic_id")
    row.ic_id = int(ic_id) if ic_id is not None else None

    success = int(data.get("success", 0) or 0)
    if success == 1 and row.ic_id:
        row.status = "issuing"
        db.commit()
        threading.Thread(
            target=_download_in_background,
            args=(row.id,),
            daemon=True,
        ).start()
    else:
        row.status = "failed"
        err = data.get("error")
        row.error_message = (err or f"apick data.success={success}")[:1000]
        db.commit()
    return row


def _download_in_background(row_id: int) -> None:
    db = SessionLocal()
    try:
        row = db.get(RegistryRequest, row_id)
        if not row or not row.ic_id:
            return
        client = ApickClient()
        max_tries = settings.DOWNLOAD_POLL_MAX_TRIES
        for i in range(max_tries):
            try:
                content, code = client.download(row.ic_id)
            except ApickError as e:
                row.status = "failed"
                row.error_message = str(e)[:1000]
                db.commit()
                return
            if code == 1 and content:
                Path(settings.STORAGE_DIR).mkdir(parents=True, exist_ok=True)
                pdf_path = os.path.join(settings.STORAGE_DIR, f"{row.ic_id}.pdf")
                with open(pdf_path, "wb") as f:
                    f.write(content)
                row.pdf_path = pdf_path
                row.status = "completed"
                row.completed_at = datetime.now(timezone.utc)
                db.commit()
                return
            if i < max_tries - 1:
                time.sleep(settings.DOWNLOAD_POLL_INTERVAL)
        row.status = "failed"
        row.error_message = "download polling exhausted"
        db.commit()
    finally:
        db.close()
