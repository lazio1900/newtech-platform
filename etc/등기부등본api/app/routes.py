import os
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import require_internal_token
from .config import settings
from .db import get_db
from .guards import GuardError
from .models import RegistryRequest
from .schemas import RegistryRequestIn, RegistryRequestOut, UsageOut
from .service import issue_or_get

router = APIRouter(
    prefix="/v1/registry",
    dependencies=[Depends(require_internal_token)],
)


def _to_out(row: RegistryRequest, include_markdown: bool = False) -> RegistryRequestOut:
    pdf_url = None
    if row.status == "completed" and row.pdf_path and row.ic_id:
        pdf_url = f"/v1/registry/{row.ic_id}/pdf"
    cached = (row.cost or 0) == 0 and row.status in ("completed", "issuing")
    return RegistryRequestOut(
        id=row.id,
        ic_id=row.ic_id,
        status=row.status,
        pdf_url=pdf_url,
        cost=row.cost or 0,
        cached=cached,
        error_message=row.error_message,
        markdown=row.markdown if include_markdown else None,
    )


@router.post("/request", response_model=RegistryRequestOut)
def request_registry(payload: RegistryRequestIn, db: Session = Depends(get_db)):
    try:
        row = issue_or_get(
            db,
            address=payload.address,
            dong=payload.dong,
            ho=payload.ho,
            type_=payload.type,
            requester_id=payload.requester_id,
            listing_id=payload.listing_id,
            force_refresh=payload.force_refresh,
        )
    except GuardError as e:
        code_map = {"disabled": 503, "daily_limit": 429, "hourly_limit": 429}
        raise HTTPException(
            status_code=code_map.get(e.code, 400),
            detail={"code": e.code, "message": e.message},
        )
    return _to_out(row)


@router.get("/{ic_id}", response_model=RegistryRequestOut)
def get_registry(ic_id: int, db: Session = Depends(get_db)):
    q = select(RegistryRequest).where(RegistryRequest.ic_id == ic_id).limit(1)
    row = db.execute(q).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "not found")
    return _to_out(row)


@router.get("/{ic_id}/markdown")
def get_registry_markdown(ic_id: int, db: Session = Depends(get_db)):
    """MinerU 가 변환한 markdown 반환. PDF 발급 완료 후에만 사용 가능.

    markdown 컬럼이 비어있고 PDF 가 disk 에 남아있으면 lazy 로 변환·저장 후 반환.
    이를 통해 markdown 캐싱 도입 *이전에* 발급된 row 도 첫 조회 시 자동 backfill 된다.
    """
    q = select(RegistryRequest).where(RegistryRequest.ic_id == ic_id).limit(1)
    row = db.execute(q).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "not found")
    if row.status != "completed":
        raise HTTPException(
            status_code=202,
            detail={"status": row.status, "error_message": row.error_message},
        )
    if not row.markdown:
        # lazy backfill: 디스크의 PDF 를 그 자리에서 MinerU 로 변환
        from .service import _convert_to_markdown
        if not row.pdf_path or not os.path.exists(row.pdf_path):
            raise HTTPException(410, {"code": "no_pdf", "message": "PDF 파일 없음"})
        with open(row.pdf_path, "rb") as f:
            pdf_bytes = f.read()
        md = _convert_to_markdown(pdf_bytes)
        if not md:
            raise HTTPException(404, {"code": "no_markdown", "message": "markdown 변환 실패"})
        row.markdown = md
        db.commit()
    return {"ic_id": ic_id, "markdown": row.markdown}


@router.get("/{ic_id}/pdf")
def get_registry_pdf(ic_id: int, db: Session = Depends(get_db)):
    q = select(RegistryRequest).where(RegistryRequest.ic_id == ic_id).limit(1)
    row = db.execute(q).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "not found")
    if row.status != "completed" or not row.pdf_path:
        raise HTTPException(
            status_code=202,
            detail={"status": row.status, "error_message": row.error_message},
        )
    if not os.path.exists(row.pdf_path):
        raise HTTPException(410, "pdf file missing")
    return FileResponse(
        row.pdf_path,
        media_type="application/pdf",
        filename=f"registry_{ic_id}.pdf",
    )


@router.get("/usage/today", response_model=UsageOut)
def usage_today(db: Session = Depends(get_db)):
    today = date.today()
    base = select(func.count(RegistryRequest.id)).where(RegistryRequest.issued_date == today)
    issued = db.execute(
        base.where(RegistryRequest.status == "completed", RegistryRequest.cost > 0)
    ).scalar() or 0
    cached = db.execute(
        base.where(RegistryRequest.status == "completed", RegistryRequest.cost == 0)
    ).scalar() or 0
    failed = db.execute(base.where(RegistryRequest.status == "failed")).scalar() or 0
    total_cost = db.execute(
        select(func.coalesce(func.sum(RegistryRequest.cost), 0)).where(
            RegistryRequest.issued_date == today
        )
    ).scalar() or 0
    return UsageOut(
        date=str(today),
        issued_count=int(issued),
        cached_count=int(cached),
        failed_count=int(failed),
        total_cost=int(total_cost),
        daily_limit=settings.DAILY_LIMIT,
        hourly_limit=settings.HOURLY_LIMIT,
    )
