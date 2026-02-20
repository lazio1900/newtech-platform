from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

import json

from core.database import get_db
from models import CrawlJob, CrawlRun, Complex, JobType, JobStatus, RunStatus

router = APIRouter()


# Pydantic schemas
class JobCreateSchema(BaseModel):
    name: str
    job_type: JobType
    description: Optional[str] = None
    target_config: Optional[str] = None
    cron_schedule: Optional[str] = None
    max_concurrency: int = 5
    rate_limit_per_minute: int = 60


class JobUpdateSchema(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    cron_schedule: Optional[str] = None
    target_config: Optional[str] = None


class JobSchema(BaseModel):
    id: int
    name: str
    job_type: JobType
    description: Optional[str]
    target_config: Optional[str]
    status: JobStatus
    cron_schedule: Optional[str]
    max_concurrency: int
    rate_limit_per_minute: int
    created_at: datetime
    updated_at: datetime
    last_run_id: Optional[int] = None
    last_run_status: Optional[str] = None
    last_run_at: Optional[datetime] = None

    class Config:
        from_attributes = True


def _resolve_complex_ids(job: CrawlJob, db: Session) -> List[int]:
    """Job의 target_config를 분석하여 수집 대상 단지 ID 목록을 반환"""
    config = json.loads(job.target_config) if job.target_config else {}

    if job.job_type == JobType.REGION_ALL:
        region_code = config.get("region_code") or config.get("sido_code", "")
        return [
            c.id for c in db.query(Complex).filter(
                Complex.region_code.like(f"{region_code}%"),
                Complex.is_active.is_(True),
            ).all()
        ]

    # complex_ids가 직접 지정된 경우
    if "complex_ids" in config:
        return config["complex_ids"]

    # 기본: 모든 활성 단지
    return [c.id for c in db.query(Complex).filter(Complex.is_active.is_(True)).all()]


def _enrich_jobs_with_last_run(jobs: list, db: Session) -> list:
    """각 Job에 최신 CrawlRun 정보를 첨부"""
    if not jobs:
        return []

    job_ids = [j.id for j in jobs]
    from sqlalchemy import func

    # 각 job_id별 최신 run 조회 (subquery로 max started_at)
    subq = (
        db.query(
            CrawlRun.job_id,
            func.max(CrawlRun.id).label("max_id"),
        )
        .filter(CrawlRun.job_id.in_(job_ids))
        .group_by(CrawlRun.job_id)
        .subquery()
    )
    latest_runs = (
        db.query(CrawlRun)
        .join(subq, CrawlRun.id == subq.c.max_id)
        .all()
    )
    run_map = {r.job_id: r for r in latest_runs}

    result = []
    for job in jobs:
        data = JobSchema.model_validate(job).model_dump()
        run = run_map.get(job.id)
        if run:
            data["last_run_id"] = run.id
            data["last_run_status"] = run.status.value if hasattr(run.status, 'value') else str(run.status)
            data["last_run_at"] = run.started_at
        result.append(data)
    return result


@router.get("/", response_model=List[JobSchema])
def list_jobs(
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[JobStatus] = None,
    db: Session = Depends(get_db),
):
    """수집 작업 목록 조회"""
    query = db.query(CrawlJob)

    if status_filter:
        query = query.filter(CrawlJob.status == status_filter)

    jobs = query.offset(skip).limit(limit).all()
    return _enrich_jobs_with_last_run(jobs, db)


@router.get("/{job_id}", response_model=JobSchema)
def get_job(job_id: int, db: Session = Depends(get_db)):
    """작업 상세 조회"""
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )

    enriched = _enrich_jobs_with_last_run([job], db)
    return enriched[0]


@router.post("/", response_model=JobSchema, status_code=status.HTTP_201_CREATED)
def create_job(
    job_data: JobCreateSchema,
    db: Session = Depends(get_db),
):
    """수집 작업 생성"""
    job = CrawlJob(**job_data.model_dump())
    db.add(job)
    db.commit()
    db.refresh(job)
    
    return job


@router.post("/create-and-run", status_code=status.HTTP_202_ACCEPTED)
def create_and_run_job(
    job_data: JobCreateSchema,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """작업 생성 + 즉시 실행"""
    job = CrawlJob(**job_data.model_dump())
    db.add(job)
    db.commit()
    db.refresh(job)

    # CrawlRun 생성
    run = CrawlRun(
        job_id=job.id,
        status=RunStatus.PENDING,
        started_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()

    complex_ids = _resolve_complex_ids(job, db)

    from services.sync_collector import collect_complex_sync
    background_tasks.add_task(collect_complex_sync, run.id, complex_ids)

    return {
        "message": "작업이 생성되고 즉시 실행되었습니다",
        "job_id": job.id,
        "run_id": run.id,
    }


@router.post("/{job_id}/run", status_code=status.HTTP_202_ACCEPTED)
def run_job_now(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """작업 즉시 실행"""
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )

    if job.status != JobStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job is not active"
        )

    # CrawlRun을 API에서 먼저 생성하여 즉시 run_id 반환
    run = CrawlRun(
        job_id=job.id,
        status=RunStatus.PENDING,
        started_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()

    complex_ids = _resolve_complex_ids(job, db)

    from services.sync_collector import collect_complex_sync
    background_tasks.add_task(collect_complex_sync, run.id, complex_ids)

    return {
        "message": "Job execution started",
        "job_id": job.id,
        "run_id": run.id,
    }


@router.patch("/{job_id}", response_model=JobSchema)
def update_job(
    job_id: int,
    update_data: JobUpdateSchema,
    db: Session = Depends(get_db),
):
    """작업 설정 수정 (이름, 설명, 스케줄, 대상 설정)"""
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    update_dict = update_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(job, key, value)

    db.commit()
    db.refresh(job)

    enriched = _enrich_jobs_with_last_run([job], db)
    return enriched[0]


@router.patch("/{job_id}/pause")
def pause_job(job_id: int, db: Session = Depends(get_db)):
    """작업 일시 중지"""
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    job.status = JobStatus.PAUSED
    db.commit()
    
    return {"message": "Job paused", "job_id": job.id}


@router.patch("/{job_id}/resume")
def resume_job(job_id: int, db: Session = Depends(get_db)):
    """작업 재개"""
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    job.status = JobStatus.ACTIVE
    db.commit()

    return {"message": "Job resumed", "job_id": job.id}


@router.post("/run-region", status_code=status.HTTP_202_ACCEPTED)
def run_region_collection_endpoint(
    region_code: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    지역 기반 전체 수집 (발견 + 시세 + 실거래가 + 매물).
    자동으로 CrawlJob(region_all)을 생성하여 작업 탭에서도 확인 가능.

    - region_code: 법정동코드 (5자리 시군구 또는 10자리)
    """
    # 같은 region_code의 기존 region_all 작업이 있으면 재사용
    target_json = json.dumps({"region_code": region_code})
    existing_job = db.query(CrawlJob).filter(
        CrawlJob.job_type == JobType.REGION_ALL,
        CrawlJob.target_config == target_json,
    ).first()

    if existing_job:
        job = existing_job
    else:
        job = CrawlJob(
            name=f"{region_code} 지역 전체 수집",
            job_type=JobType.REGION_ALL,
            description=f"지역코드 {region_code} 단지발견 + 시세 + 실거래 + 매물",
            target_config=target_json,
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

    # 해당 지역 활성 단지 조회
    complex_ids = [
        c.id for c in db.query(Complex).filter(
            Complex.region_code.like(f"{region_code}%"),
            Complex.is_active.is_(True),
        ).all()
    ]

    from services.sync_collector import collect_complex_sync
    background_tasks.add_task(collect_complex_sync, run.id, complex_ids)

    return {
        "message": f"{region_code} 지역 수집이 시작되었습니다",
        "run_id": run.id,
        "job_id": job.id,
    }
