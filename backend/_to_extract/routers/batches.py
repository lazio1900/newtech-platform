"""
배치 설정 API — 시/도별 정기 크롤링 관리.

각 시/도는 하나의 CrawlJob(job_type=REGION_ALL)에 매핑되며,
해당 시/도에 등록된 모든 단지를 대상으로 수집합니다.
"""
from typing import Any, Dict, List, Optional
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
import json

from core.database import get_db
from models import Complex, CrawlJob, CrawlRun, JobType, JobStatus, RunStatus


router = APIRouter()

# 시/도 코드 → 이름 매핑 (프론트엔드 SIDO_REGIONS 동일)
SIDO_MAP: Dict[str, str] = {
    "11": "서울", "26": "부산", "27": "대구", "28": "인천",
    "29": "광주", "30": "대전", "31": "울산", "36": "세종",
    "41": "경기", "43": "충북", "44": "충남", "45": "전북",
    "46": "전남", "47": "경북", "48": "경남", "50": "제주",
}


def _find_batch_job(db: Session, sido_code: str) -> Optional[CrawlJob]:
    """시/도에 해당하는 배치 CrawlJob 조회"""
    target_json = json.dumps({"sido_code": sido_code})
    return db.query(CrawlJob).filter(
        CrawlJob.job_type == JobType.REGION_ALL,
        CrawlJob.target_config == target_json,
    ).first()


class BatchRunSchema(BaseModel):
    id: int
    status: str
    started_at: Optional[str]
    finished_at: Optional[str]
    total_tasks: int
    success_count: int
    failed_count: int
    skipped_count: int


class BatchSchema(BaseModel):
    sido_code: str
    sido_name: str
    complex_count: int
    job_id: Optional[int]
    job_status: Optional[str]
    cron_schedule: Optional[str]
    last_runs: List[BatchRunSchema]


@router.get("/", response_model=List[BatchSchema])
def list_batches(db: Session = Depends(get_db)):
    """시/도별 배치 목록 (단지 수, 스케줄, 최근 실행 포함)"""
    # 시/도별 단지 수 집계
    rows = (
        db.query(
            func.substr(Complex.region_code, 1, 2).label("sido"),
            func.count(Complex.id).label("cnt"),
        )
        .filter(Complex.region_code.isnot(None), Complex.is_active.is_(True))
        .group_by("sido")
        .all()
    )
    count_map = {r.sido: r.cnt for r in rows}

    # 배치용 CrawlJob 전체 조회
    jobs = (
        db.query(CrawlJob)
        .filter(CrawlJob.job_type == JobType.REGION_ALL)
        .all()
    )
    job_map: Dict[str, CrawlJob] = {}
    for j in jobs:
        try:
            cfg = json.loads(j.target_config) if j.target_config else {}
            if "sido_code" in cfg:
                job_map[cfg["sido_code"]] = j
        except (json.JSONDecodeError, TypeError):
            pass

    result: List[BatchSchema] = []
    for sido_code, sido_name in SIDO_MAP.items():
        job = job_map.get(sido_code)
        last_runs: List[BatchRunSchema] = []

        if job:
            runs = (
                db.query(CrawlRun)
                .filter(CrawlRun.job_id == job.id)
                .order_by(CrawlRun.created_at.desc())
                .limit(5)
                .all()
            )
            for r in runs:
                last_runs.append(BatchRunSchema(
                    id=r.id,
                    status=r.status.value if hasattr(r.status, "value") else str(r.status),
                    started_at=r.started_at.isoformat() if r.started_at else None,
                    finished_at=r.finished_at.isoformat() if r.finished_at else None,
                    total_tasks=r.total_tasks,
                    success_count=r.success_count,
                    failed_count=r.failed_count,
                    skipped_count=r.skipped_count,
                ))

        result.append(BatchSchema(
            sido_code=sido_code,
            sido_name=sido_name,
            complex_count=count_map.get(sido_code, 0),
            job_id=job.id if job else None,
            job_status=job.status.value if job else None,
            cron_schedule=job.cron_schedule if job else None,
            last_runs=last_runs,
        ))

    return result


@router.post("/{sido_code}/run", status_code=status.HTTP_202_ACCEPTED)
def run_batch(
    sido_code: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """시/도 배치 즉시 실행 — 해당 시/도의 모든 활성 단지 수집"""
    if sido_code not in SIDO_MAP:
        raise HTTPException(status_code=400, detail=f"Invalid sido_code: {sido_code}")

    complexes = (
        db.query(Complex)
        .filter(
            Complex.region_code.like(f"{sido_code}%"),
            Complex.is_active.is_(True),
        )
        .all()
    )
    if not complexes:
        raise HTTPException(
            status_code=404,
            detail=f"{SIDO_MAP[sido_code]}에 등록된 단지가 없습니다",
        )

    # 배치 Job이 없으면 생성
    job = _find_batch_job(db, sido_code)
    if not job:
        job = CrawlJob(
            name=f"{SIDO_MAP[sido_code]} 배치 수집",
            job_type=JobType.REGION_ALL,
            target_config=json.dumps({"sido_code": sido_code}),
            status=JobStatus.ACTIVE,
        )
        db.add(job)
        db.commit()

    # CrawlRun 생성
    run = CrawlRun(
        job_id=job.id,
        status=RunStatus.PENDING,
        started_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()

    complex_ids = [c.id for c in complexes]

    from services.sync_collector import collect_complex_sync
    background_tasks.add_task(collect_complex_sync, run.id, complex_ids)

    return {
        "message": f"{SIDO_MAP[sido_code]} {len(complexes)}개 단지 수집 시작",
        "run_id": run.id,
        "complex_count": len(complexes),
    }


class ScheduleUpdateSchema(BaseModel):
    cron_schedule: Optional[str] = None


@router.patch("/{sido_code}/schedule")
def update_batch_schedule(
    sido_code: str,
    body: ScheduleUpdateSchema,
    db: Session = Depends(get_db),
):
    """시/도 배치 스케줄 설정/수정"""
    if sido_code not in SIDO_MAP:
        raise HTTPException(status_code=400, detail=f"Invalid sido_code: {sido_code}")

    job = _find_batch_job(db, sido_code)
    if not job:
        job = CrawlJob(
            name=f"{SIDO_MAP[sido_code]} 배치 수집",
            job_type=JobType.REGION_ALL,
            target_config=json.dumps({"sido_code": sido_code}),
            status=JobStatus.ACTIVE,
        )
        db.add(job)

    job.cron_schedule = body.cron_schedule
    db.commit()

    return {
        "message": "스케줄이 저장되었습니다",
        "sido_code": sido_code,
        "cron_schedule": job.cron_schedule,
    }
