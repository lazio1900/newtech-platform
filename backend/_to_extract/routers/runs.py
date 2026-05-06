from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from core.database import get_db
from models import Complex, CrawlRun, CrawlTask, RunStatus, TaskStatus

router = APIRouter()


# Pydantic schemas
class TaskSchema(BaseModel):
    id: int
    task_key: str
    status: TaskStatus
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    retry_count: int
    items_collected: int
    items_saved: int
    error_type: Optional[str]
    error_message: Optional[str]

    class Config:
        from_attributes = True


class RunSchema(BaseModel):
    id: int
    job_id: Optional[int]
    status: RunStatus
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    total_tasks: int
    success_count: int
    failed_count: int
    skipped_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class TargetComplexSchema(BaseModel):
    id: int
    name: str
    address: str
    region_code: Optional[str]


class RunDetailSchema(RunSchema):
    tasks: List[TaskSchema] = []
    target_complexes: List[TargetComplexSchema] = []


def _extract_complex_ids_from_tasks(tasks) -> List[int]:
    """task_key에서 complex_id를 추출"""
    cids: set[int] = set()
    for task in tasks:
        parts = task.task_key.split("_")
        try:
            if parts[0] == "kb" and len(parts) >= 3:
                cids.add(int(parts[2]))
        except (ValueError, IndexError):
            continue
    return sorted(cids)


class RunListItemSchema(RunSchema):
    target_summary: str = ""


@router.get("/", response_model=List[RunListItemSchema])
def list_runs(
    skip: int = 0,
    limit: int = 100,
    job_id: Optional[int] = None,
    status_filter: Optional[RunStatus] = None,
    db: Session = Depends(get_db),
):
    """실행 이력 목록 조회"""
    query = db.query(CrawlRun).order_by(CrawlRun.created_at.desc())

    if job_id:
        query = query.filter(CrawlRun.job_id == job_id)

    if status_filter:
        query = query.filter(CrawlRun.status == status_filter)

    runs = query.offset(skip).limit(limit).all()

    # 각 run의 대상 단지 요약 생성
    results = []
    for run in runs:
        cids = _extract_complex_ids_from_tasks(run.tasks)
        summary = ""
        if cids:
            complexes = db.query(Complex).filter(Complex.id.in_(cids)).all()
            names = [c.name for c in complexes]
            if len(names) <= 3:
                summary = ", ".join(names)
            else:
                summary = f"{names[0]} 외 {len(names) - 1}개 단지"

        item = RunListItemSchema.model_validate(run)
        item.target_summary = summary
        results.append(item)

    return results


@router.get("/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    """실행 상세 조회 (태스크 + 대상 단지 포함)"""
    run = db.query(CrawlRun).filter(CrawlRun.id == run_id).first()

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found"
        )

    cids = _extract_complex_ids_from_tasks(run.tasks)
    target_complexes = []
    if cids:
        complexes = db.query(Complex).filter(Complex.id.in_(cids)).all()
        target_complexes = [
            TargetComplexSchema(
                id=c.id, name=c.name, address=c.address, region_code=c.region_code,
            )
            for c in complexes
        ]

    detail = RunDetailSchema.model_validate(run)
    detail.target_complexes = target_complexes
    return detail


@router.get("/{run_id}/tasks", response_model=List[TaskSchema])
def get_run_tasks(
    run_id: int,
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[TaskStatus] = None,
    db: Session = Depends(get_db),
):
    """실행의 태스크 목록 조회"""
    query = db.query(CrawlTask).filter(CrawlTask.run_id == run_id)
    
    if status_filter:
        query = query.filter(CrawlTask.status == status_filter)
    
    tasks = query.offset(skip).limit(limit).all()
    return tasks
