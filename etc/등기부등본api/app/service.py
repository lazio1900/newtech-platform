import os
import re
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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

# apick 의 address 필드 validation: 한글/영문/숫자/공백/하이픈/언더스코어 만 허용.
# 단지명에 괄호("신내(6단지)") 나 마침표 등이 들어가면 거부되므로 호출 직전 sanitize.
_APICK_DISALLOWED = re.compile(r"[^\w가-힣\s\-]")


def _sanitize_for_apick(s: str) -> str:
    """apick 호출용 주소에서 허용 외 문자 제거 및 공백 정규화."""
    cleaned = _APICK_DISALLOWED.sub("", s)
    return _whitespace.sub(" ", cleaned).strip()


# 'requested' 상태가 이 시간보다 오래 머물러 있으면 stuck (이전 시도가 commit 전에 끊김) 으로 간주.
STALE_REQUESTED_SECONDS = 300

# 매칭 실패 시 시도할 단지명 표기 변형. 영문↔한글 브랜드명 차이가 IROS 색인과
# 일치하지 않아 0건이 자주 나옴. 양방향 페어로 정의 — apick 비용 절약 위해 최대 3개.
_BRAND_VARIANTS = [
    ("e편한세상", "이편한세상"),
    ("e-편한세상", "이편한세상"),
    ("이-편한세상", "이편한세상"),
]


def _address_variants(address: str, max_count: int = 3) -> list[str]:
    """단지명 표기 차이로 인한 매칭 실패 시 시도할 후보 주소 리스트.

    양방향(영→한, 한→영) 모두 생성. 원본과 동일한 변형은 제외.
    """
    variants: list[str] = []
    seen: set[str] = {address}
    for left, right in _BRAND_VARIANTS:
        for src, dst in ((left, right), (right, left)):
            if src in address:
                v = address.replace(src, dst)
                if v not in seen:
                    variants.append(v)
                    seen.add(v)
                if len(variants) >= max_count:
                    return variants
    return variants


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
    """오늘자 발급 row 중 캐시/진행중 반환용.

    - completed / issuing: 항상 반환 (캐시 hit, 진행중 폴링 가능)
    - requested: 5분 이내만 반환 (in-flight 진행중). 그 이상은 stuck 으로 간주해 None
    - failed: None (재시도 허용)
    """
    q = (
        select(RegistryRequest)
        .where(
            RegistryRequest.address_norm == address_norm,
            RegistryRequest.type == type_,
            RegistryRequest.issued_date == date.today(),
            RegistryRequest.status.in_(("issuing", "completed", "requested")),
        )
        .order_by(RegistryRequest.id.desc())
        .limit(1)
    )
    row = db.execute(q).scalar_one_or_none()
    if row and row.status == "requested":
        age = (datetime.now(timezone.utc) - row.created_at).total_seconds()
        if age > STALE_REQUESTED_SECONDS:
            return None
    return row


def _find_today_any(
    db: Session, address_norm: str, type_: str
) -> Optional[RegistryRequest]:
    """오늘자 row 를 상태 무관하게 1건 반환 (race condition 재조회용)."""
    q = (
        select(RegistryRequest)
        .where(
            RegistryRequest.address_norm == address_norm,
            RegistryRequest.type == type_,
            RegistryRequest.issued_date == date.today(),
        )
        .order_by(RegistryRequest.id.desc())
        .limit(1)
    )
    return db.execute(q).scalar_one_or_none()


def _clear_today_blocking_rows(
    db: Session, address_norm: str, type_: str, clear_active: bool = False
) -> None:
    """INSERT 직전 unique constraint (address, type, issued_date) 위반 가능 row 삭제.

    - 기본: stale 'requested' + 'failed' (캐시 반환되지 않는 상태들)
    - clear_active=True (force_refresh): 'issuing' / 'completed' 까지 모두 삭제
    """
    statuses = ["requested", "failed"]
    if clear_active:
        statuses += ["issuing", "completed"]
    q = select(RegistryRequest).where(
        RegistryRequest.address_norm == address_norm,
        RegistryRequest.type == type_,
        RegistryRequest.issued_date == date.today(),
        RegistryRequest.status.in_(statuses),
    )
    rows = db.execute(q).scalars().all()
    for r in rows:
        db.delete(r)
    if rows:
        db.commit()


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

    # INSERT 직전 unique constraint 차단 row 청소.
    # - force_refresh: 오늘자 row 전부 삭제 (강제 재발급 의도)
    # - 일반 경로: stale 'requested' / 'failed' 만 삭제. 'issuing'/'completed' 는 위 cache 단계에서 이미 반환됨.
    _clear_today_blocking_rows(db, address_norm, type_, clear_active=force_refresh)

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
    try:
        db.commit()
    except IntegrityError:
        # 동시 요청 race 또는 위 청소가 못 잡은 잔여 — 기존 row 재조회 후 반환.
        db.rollback()
        existing = _find_today_any(db, address_norm, type_)
        if existing:
            return existing
        raise
    db.refresh(row)

    client = ApickClient()
    search_address = normalize_address(address, dong, ho)
    apick_address = _sanitize_for_apick(search_address)
    try:
        body = client.request_iros(apick_address, type_)
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
        # 매칭 실패 시 단지명 변형(영문↔한글 등) 자동 재시도
        variant_ic_id: Optional[int] = None
        for v_addr in _address_variants(search_address):
            try:
                v_body = client.request_iros(_sanitize_for_apick(v_addr), type_)
            except ApickError:
                continue
            v_api = v_body.get("api", {}) or {}
            v_data = v_body.get("data", {}) or {}
            # 추가 비용 누적 기록
            row.cost = (row.cost or 0) + int(v_api.get("cost", 0) or 0)
            v_success = int(v_data.get("success", 0) or 0)
            v_ic_raw = v_data.get("ic_id")
            if v_success == 1 and v_ic_raw is not None:
                variant_ic_id = int(v_ic_raw)
                row.apick_pl_id = v_api.get("pl_id")
                break

        if variant_ic_id:
            row.ic_id = variant_ic_id
            row.status = "issuing"
            row.error_message = None
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
