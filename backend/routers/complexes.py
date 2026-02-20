from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from core.database import get_db
from models import Complex, Area, PriorityLevel
from models.crawl import CrawlRun, CrawlTask, RunStatus, TaskStatus

router = APIRouter()


# Pydantic schemas
class AreaSchema(BaseModel):
    id: Optional[int] = None
    exclusive_m2: float
    supply_m2: Optional[float] = None
    pyeong: Optional[float] = None
    kb_area_code: Optional[str] = None

    class Config:
        from_attributes = True


class ComplexCreateSchema(BaseModel):
    name: str
    address: str
    region_code: Optional[str] = None
    kb_complex_id: Optional[str] = None
    priority: PriorityLevel = PriorityLevel.NORMAL
    is_active: bool = True
    collect_listings: bool = True


class ComplexSchema(BaseModel):
    id: int
    name: str
    address: str
    region_code: Optional[str]
    kb_complex_id: Optional[str]
    priority: PriorityLevel
    is_active: bool
    collect_listings: bool
    total_households: Optional[int] = None
    corridor_type: Optional[str] = None
    build_year: Optional[int] = None
    areas: List[AreaSchema] = []

    class Config:
        from_attributes = True


class PaginatedComplexResponse(BaseModel):
    items: List[ComplexSchema]
    total: int


@router.get("/", response_model=PaginatedComplexResponse)
def list_complexes(
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    region_code: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """단지 목록 조회 (서버 사이드 페이지네이션)"""
    query = db.query(Complex)

    if is_active is not None:
        query = query.filter(Complex.is_active == is_active)

    if region_code:
        query = query.filter(Complex.region_code.like(f"{region_code}%"))

    if search:
        q = f"%{search}%"
        query = query.filter(
            (Complex.name.ilike(q))
            | (Complex.address.ilike(q))
            | (Complex.kb_complex_id.ilike(q))
            | (Complex.region_code.ilike(q))
        )

    total = query.count()
    items = query.order_by(Complex.name).offset(skip).limit(limit).all()
    return PaginatedComplexResponse(items=items, total=total)


@router.get("/region-counts")
def get_region_counts(db: Session = Depends(get_db)):
    """시/도별, 시/군/구별 단지 수 조회"""
    complexes = db.query(Complex.region_code).filter(Complex.region_code.isnot(None)).all()

    sido: Dict[str, int] = {}
    region: Dict[str, int] = {}
    for (code,) in complexes:
        if code and len(code) >= 2:
            key = code[:2]
            sido[key] = sido.get(key, 0) + 1
        if code and len(code) >= 5:
            key = code[:5]
            region[key] = region.get(key, 0) + 1

    return {"sido_counts": sido, "region_counts": region}


@router.get("/last-runs")
def get_complex_last_runs(db: Session = Depends(get_db)):
    """각 단지의 마지막 수집 상태를 반환"""
    # CrawlTask.task_key에서 complex_id를 추출하여 가장 최신 run 정보를 매핑
    # task_key format: kb_price_{complex_id}_{area_id}, kb_transaction_{complex_id}, kb_listing_{complex_id}
    from sqlalchemy import text

    # 모든 task를 가져와 complex_id별 가장 최신 run 정보를 추출
    tasks = (
        db.query(CrawlTask, CrawlRun)
        .join(CrawlRun, CrawlTask.run_id == CrawlRun.id)
        .order_by(CrawlRun.started_at.desc())
        .all()
    )

    result: Dict[int, Any] = {}
    for task, run in tasks:
        # task_key에서 complex_id 추출
        parts = task.task_key.split("_")
        try:
            # kb_price_3_1 → complex_id=3, kb_transaction_3 → complex_id=3
            if parts[0] == "kb" and len(parts) >= 3:
                cid = int(parts[2])
            else:
                continue
        except (ValueError, IndexError):
            continue

        if cid not in result:
            result[cid] = {
                "run_id": run.id,
                "status": run.status.value if hasattr(run.status, 'value') else str(run.status),
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            }

    return result


@router.get("/regions/sigungu")
async def get_sigungu_list(sido_code: str):
    """
    시도코드(2자리)로 해당 시도의 시군구 목록을 KB부동산 API에서 조회.
    예: sido_code="11" → 서울시 시군구 목록
    """
    sido_map = {
        "11": "서울시", "26": "부산시", "27": "대구시", "28": "인천시",
        "29": "광주시", "30": "대전시", "31": "울산시", "36": "세종시",
        "41": "경기도", "42": "강원도", "43": "충청북도", "44": "충청남도",
        "45": "전라북도", "46": "전라남도", "47": "경상북도", "48": "경상남도",
        "50": "제주도",
    }
    sido_name = sido_map.get(sido_code)
    if not sido_name:
        raise HTTPException(status_code=400, detail=f"Invalid sido_code: {sido_code}")

    from connectors.kb_base import KBBaseConnector
    from connectors.kb_endpoints import REGION_SIGUNGU

    class _RegionConnector(KBBaseConnector):
        def _build_http_params(self, **kw): return (REGION_SIGUNGU, kw)
        def _build_browser_config(self, **kw): return ("", "", None)
        def parse(self, raw): return []
        def fetch(self, **kw): return {}

    connector = _RegionConnector(name="RegionLookup", rate_limit_per_minute=30)
    try:
        data = await connector._fetch_via_http(REGION_SIGUNGU, {"시도명": sido_name})
        sigungu_list = data.get("dataBody", {}).get("data", [])
        return [
            {
                "code": item.get("법정동코드", "")[:5],
                "name": item.get("시군구명", ""),
                "lat": item.get("wgs84중심위도"),
                "lng": item.get("wgs84중심경도"),
            }
            for item in sigungu_list
            if item.get("법정동코드")
        ]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"KB API 조회 실패: {str(e)}")


@router.get("/{complex_id}", response_model=ComplexSchema)
def get_complex(complex_id: int, db: Session = Depends(get_db)):
    """단지 상세 조회"""
    complex = db.query(Complex).filter(Complex.id == complex_id).first()
    
    if not complex:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complex not found"
        )
    
    return complex


@router.post("/", response_model=ComplexSchema, status_code=status.HTTP_201_CREATED)
def create_complex(
    complex_data: ComplexCreateSchema,
    db: Session = Depends(get_db),
):
    """단지 등록"""
    complex = Complex(**complex_data.model_dump())
    db.add(complex)
    db.commit()
    db.refresh(complex)
    
    return complex


@router.patch("/{complex_id}", response_model=ComplexSchema)
def update_complex(
    complex_id: int,
    complex_data: dict,
    db: Session = Depends(get_db),
):
    """단지 정보 수정"""
    complex = db.query(Complex).filter(Complex.id == complex_id).first()
    
    if not complex:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complex not found"
        )
    
    for key, value in complex_data.items():
        if hasattr(complex, key):
            setattr(complex, key, value)
    
    db.commit()
    db.refresh(complex)
    
    return complex


@router.delete("/{complex_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_complex(complex_id: int, db: Session = Depends(get_db)):
    """단지 삭제"""
    complex = db.query(Complex).filter(Complex.id == complex_id).first()
    
    if not complex:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complex not found"
        )
    
    db.delete(complex)
    db.commit()

    return None


@router.post("/{complex_id}/collect", status_code=status.HTTP_202_ACCEPTED)
def collect_complex(
    complex_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """단지 즉시 수집 (시세 + 매물) — Celery 없이 백그라운드 실행"""
    complex_obj = db.query(Complex).filter(Complex.id == complex_id).first()
    if not complex_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complex not found",
        )

    run = CrawlRun(
        job_id=None,
        status=RunStatus.PENDING,
        started_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()

    from services.sync_collector import collect_complex_sync
    background_tasks.add_task(collect_complex_sync, run.id, [complex_id])

    return {
        "message": f"{complex_obj.name} 수집이 시작되었습니다",
        "run_id": run.id,
    }


class BatchCollectSchema(BaseModel):
    complex_ids: List[int]


@router.post("/batch-collect", status_code=status.HTTP_202_ACCEPTED)
def batch_collect_complexes(
    body: BatchCollectSchema,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """여러 단지 일괄 수집 — Celery 없이 백그라운드 실행"""
    if not body.complex_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="complex_ids is empty",
        )

    complexes = (
        db.query(Complex)
        .filter(Complex.id.in_(body.complex_ids))
        .all()
    )
    if not complexes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No complexes found",
        )

    run = CrawlRun(
        job_id=None,
        status=RunStatus.PENDING,
        started_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()

    from services.sync_collector import collect_complex_sync
    background_tasks.add_task(collect_complex_sync, run.id, body.complex_ids)

    return {
        "message": f"{len(complexes)}개 단지 수집이 시작되었습니다",
        "run_id": run.id,
        "count": len(complexes),
    }


@router.get("/runs/{run_id}/status")
def get_run_status(run_id: int, db: Session = Depends(get_db)):
    """수집 실행 상태 폴링"""
    run = db.query(CrawlRun).filter(CrawlRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    tasks = db.query(CrawlTask).filter(CrawlTask.run_id == run_id).all()

    return {
        "run_id": run.id,
        "status": run.status.value,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "total_tasks": run.total_tasks or 0,
        "success_count": run.success_count or 0,
        "failed_count": run.failed_count or 0,
        "tasks": [
            {
                "task_key": t.task_key,
                "status": t.status.value,
                "items_collected": t.items_collected or 0,
                "items_saved": t.items_saved or 0,
                "error_message": t.error_message,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "finished_at": t.finished_at.isoformat() if t.finished_at else None,
            }
            for t in tasks
        ],
    }


@router.post("/discover-region")
async def discover_region(
    region_code: str,
    db: Session = Depends(get_db),
):
    """
    지역코드로 아파트 단지 자동 발견 및 등록.

    동기 실행 후 결과를 바로 반환합니다.

    - region_code: 법정동코드 (5자리 시군구 또는 10자리 법정동)
    - 예: "11680" (강남구), "1168010100" (역삼동)
    """
    from services.complex_discovery import ComplexDiscoveryService

    service = ComplexDiscoveryService(db)
    result = await service.discover_complexes(region_code)

    return {
        "region_code": result["region_code"],
        "total_found": result["total_found"],
        "new_registered": result["new_registered"],
        "already_exists": result["already_exists"],
    }
