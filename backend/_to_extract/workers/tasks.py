"""
Celery 태스크 정의.

KB부동산 데이터 수집 태스크:
- KB 시세 수집 (단지/면적별)
- KB 실거래가 수집 (단지별)
- KB 매물 수집 (단지별)
- 지역 기반 단지 발견
- 지역 기반 전체 수집
"""
import asyncio
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

from celery import Task
from sqlalchemy.orm import Session

from workers.celery_app import celery_app
from core.database import SessionLocal
from models import (
    CrawlRun, CrawlTask, Complex, Area,
    KBPrice, Transaction, Listing, ListingStatus,
    RunStatus, TaskStatus,
)
from connectors import KBPriceConnector, KBTransactionConnector, KBListingConnector

logger = logging.getLogger(__name__)


def run_async(coro):
    """async 코루틴을 동기적으로 실행하는 헬퍼."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def ensure_complex_areas(db: Session, complex_obj: Complex) -> List[Area]:
    """
    단지에 면적 정보가 없으면 KB API에서 조회하여 자동 등록.
    지역 발견 시 면적 정보 없이 등록된 단지를 위한 보완 로직.
    """
    if complex_obj.areas:
        return complex_obj.areas

    if not complex_obj.kb_complex_id:
        logger.warning(f"Complex {complex_obj.id} ({complex_obj.name}): no kb_complex_id, skip area fetch")
        return []

    logger.info(f"Complex {complex_obj.id} ({complex_obj.name}): fetching areas from KB API")

    try:
        from connectors.kb_endpoints import COMPLEX_TYPE_INFO
        from services.complex_discovery import _DiscoveryConnector

        connector = _DiscoveryConnector(name="area_fetch", rate_limit_per_minute=30)
        data = run_async(
            connector._fetch_via_http(
                COMPLEX_TYPE_INFO, {"단지기본일련번호": complex_obj.kb_complex_id}
            )
        )

        body = data.get("dataBody", {}).get("data", [])
        area_list = body if isinstance(body, list) else []

        created = []
        for a in area_list:
            exclusive = a.get("전용면적", 0)
            try:
                exclusive = float(str(exclusive).replace(",", ""))
            except (ValueError, TypeError):
                continue
            if exclusive <= 0:
                continue

            supply = None
            try:
                supply = float(str(a.get("공급면적", "")).replace(",", "")) or None
            except (ValueError, TypeError):
                pass

            pyeong = None
            try:
                pyeong = float(str(a.get("평", "")).replace(",", "")) or None
            except (ValueError, TypeError):
                pass

            area_code = str(a.get("면적일련번호", "")) or None

            area = Area(
                complex_id=complex_obj.id,
                exclusive_m2=exclusive,
                supply_m2=supply,
                pyeong=pyeong,
                kb_area_code=area_code,
            )
            db.add(area)
            created.append(area)

        if created:
            db.flush()
            logger.info(f"Complex {complex_obj.id}: registered {len(created)} areas")
        else:
            logger.warning(f"Complex {complex_obj.id}: no valid areas from KB API")

        return created

    except Exception as e:
        logger.warning(f"Complex {complex_obj.id}: area fetch failed: {e}")
        return []


def _get_target_complexes(
    db: Session, target_config: Optional[str] = None
) -> List[Complex]:
    """
    target_config에서 대상 단지 목록을 결정.
    - complex_ids가 있으면 해당 단지만 (활성 여부 무관)
    - 없으면 모든 활성 단지
    """
    if target_config:
        try:
            config = json.loads(target_config)
        except (json.JSONDecodeError, TypeError):
            config = {}

        complex_ids = config.get("complex_ids")
        if complex_ids and isinstance(complex_ids, list):
            return db.query(Complex).filter(Complex.id.in_(complex_ids)).all()

    return db.query(Complex).filter(Complex.is_active == True).all()


def _finalize_run_if_complete(db: Session, run_id: int):
    """
    Run에 속한 모든 태스크가 완료(success/failed/skipped)되었는지 확인하고,
    모두 끝났으면 Run 상태를 성공/실패/부분성공으로 갱신.
    """
    run = db.query(CrawlRun).filter(CrawlRun.id == run_id).first()
    if not run or run.status not in (RunStatus.RUNNING,):
        return

    total = run.total_tasks or 0
    if total == 0:
        return

    finished_statuses = {TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.SKIPPED}
    tasks = db.query(CrawlTask).filter(CrawlTask.run_id == run_id).all()
    finished = [t for t in tasks if t.status in finished_statuses]

    if len(finished) < total:
        return  # 아직 진행 중

    success = sum(1 for t in finished if t.status == TaskStatus.SUCCESS)
    failed = sum(1 for t in finished if t.status == TaskStatus.FAILED)
    skipped = sum(1 for t in finished if t.status == TaskStatus.SKIPPED)

    run.success_count = success
    run.failed_count = failed
    run.skipped_count = skipped
    run.finished_at = datetime.utcnow()

    if failed == 0:
        run.status = RunStatus.SUCCESS
    elif success == 0:
        run.status = RunStatus.FAILED
    else:
        run.status = RunStatus.PARTIAL

    db.commit()
    logger.info(
        f"Run {run_id} finalized: {run.status.value} "
        f"(success={success}, failed={failed}, skipped={skipped})"
    )


class DatabaseTask(Task):
    """Base task with database session management"""

    _db: Session = None

    @property
    def db(self):
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    def after_return(self, *args, **kwargs):
        if self._db is not None:
            self._db.close()
            self._db = None


# =============================================================================
# KB 시세 수집
# =============================================================================

@celery_app.task(base=DatabaseTask, bind=True)
def collect_kb_price_task(
    self,
    run_id: int,
    complex_id: int,
    area_id: int,
) -> Dict[str, Any]:
    """단일 단지/면적에 대한 KB 시세 수집 태스크"""
    db = self.db
    task_key = f"kb_price_{complex_id}_{area_id}"

    task_record = CrawlTask(
        run_id=run_id,
        task_key=task_key,
        status=TaskStatus.RUNNING,
        started_at=datetime.utcnow(),
    )
    db.add(task_record)
    db.commit()

    try:
        connector = KBPriceConnector(db_session=db)
        result = connector.collect(complex_id=complex_id, area_id=area_id)

        items_saved = 0
        for item in result["items"]:
            existing = db.query(KBPrice).filter(
                KBPrice.complex_id == complex_id,
                KBPrice.area_id == area_id,
                KBPrice.as_of_date == item["as_of_date"],
            ).first()

            if existing:
                existing.general_price = item["general_price"]
                existing.high_avg_price = item["high_avg_price"]
                existing.low_avg_price = item["low_avg_price"]
                existing.fetched_at = datetime.utcnow()
                existing.parser_version = item.get("parser_version")
            else:
                db.add(KBPrice(
                    complex_id=complex_id,
                    area_id=area_id,
                    as_of_date=item["as_of_date"],
                    general_price=item["general_price"],
                    high_avg_price=item["high_avg_price"],
                    low_avg_price=item["low_avg_price"],
                    source=item["source"],
                    fetched_at=datetime.utcnow(),
                    parser_version=item.get("parser_version"),
                ))
            items_saved += 1

        # 최근실거래가 추출 (BasePrcInfoNew 응답에 포함)
        raw_data = result.get("raw")
        if raw_data:
            area_obj = db.get(Area, area_id)
            exclusive_m2 = (area_obj.exclusive_m2 if area_obj and area_obj.exclusive_m2 else None)

            tx_data = connector.parse_recent_transaction(raw_data)
            if tx_data and exclusive_m2 is not None:
                existing_tx = db.query(Transaction).filter(
                    Transaction.complex_id == complex_id,
                    Transaction.contract_date == tx_data["contract_date"],
                    Transaction.price == tx_data["price"],
                    Transaction.exclusive_m2 == exclusive_m2,
                ).first()
                if not existing_tx:
                    db.add(Transaction(
                        complex_id=complex_id,
                        contract_date=tx_data["contract_date"],
                        price=tx_data["price"],
                        exclusive_m2=exclusive_m2,
                        floor=tx_data.get("floor"),
                        source="kb",
                        fetched_at=datetime.utcnow(),
                    ))
                    items_saved += 1

        db.commit()
        task_record.status = TaskStatus.SUCCESS
        task_record.items_collected = len(result["items"])
        task_record.items_saved = items_saved
        logger.info(f"Task {task_key} completed: {len(result['items'])} prices, {items_saved} total saved")
        return {"status": "success", "items_collected": len(result["items"])}

    except BaseException as e:
        logger.exception(f"Task {task_key} failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        task_record.status = TaskStatus.FAILED
        task_record.error_type = type(e).__name__
        task_record.error_message = str(e)[:500]
        return {"status": "failed", "error": str(e)}

    finally:
        task_record.finished_at = datetime.utcnow()
        try:
            db.commit()
        except Exception:
            pass
        _finalize_run_if_complete(db, run_id)


# =============================================================================
# KB 실거래가 수집
# =============================================================================

@celery_app.task(base=DatabaseTask, bind=True)
def collect_kb_transaction_task(
    self,
    run_id: int,
    complex_id: int,
) -> Dict[str, Any]:
    """단일 단지에 대한 KB 실거래가 수집 태스크"""
    db = self.db
    task_key = f"kb_transaction_{complex_id}"

    task_record = CrawlTask(
        run_id=run_id,
        task_key=task_key,
        status=TaskStatus.RUNNING,
        started_at=datetime.utcnow(),
    )
    db.add(task_record)
    db.commit()

    try:
        connector = KBTransactionConnector(db_session=db)
        result = connector.collect(complex_id=complex_id)

        saved_count = 0
        for item in result["items"]:
            transaction = Transaction(
                complex_id=complex_id,
                contract_date=item["contract_date"],
                price=item["price"],
                exclusive_m2=item["exclusive_m2"],
                floor=item.get("floor"),
                is_cancelled=item.get("is_cancelled", False),
                source="kb",
                fetched_at=datetime.utcnow(),
            )
            db.merge(transaction)
            saved_count += 1

        db.commit()
        task_record.status = TaskStatus.SUCCESS
        task_record.items_collected = len(result["items"])
        task_record.items_saved = saved_count
        logger.info(f"Task {task_key} completed: {len(result['items'])} items")
        return {"status": "success", "items_collected": len(result["items"])}

    except BaseException as e:
        logger.exception(f"Task {task_key} failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        task_record.status = TaskStatus.FAILED
        task_record.error_type = type(e).__name__
        task_record.error_message = str(e)[:500]
        return {"status": "failed", "error": str(e)}

    finally:
        task_record.finished_at = datetime.utcnow()
        try:
            db.commit()
        except Exception:
            pass
        _finalize_run_if_complete(db, run_id)


# =============================================================================
# KB 매물 수집
# =============================================================================

@celery_app.task(base=DatabaseTask, bind=True)
def collect_kb_listing_task(
    self,
    run_id: int,
    complex_id: int,
) -> Dict[str, Any]:
    """단일 단지에 대한 KB 매물 수집 태스크"""
    db = self.db
    task_key = f"kb_listing_{complex_id}"

    task_record = CrawlTask(
        run_id=run_id,
        task_key=task_key,
        status=TaskStatus.RUNNING,
        started_at=datetime.utcnow(),
    )
    db.add(task_record)
    db.commit()

    try:
        connector = KBListingConnector(db_session=db)
        result = connector.collect(complex_id=complex_id)

        saved_count = 0
        seen_ids = set()

        for item in result["items"]:
            listing_id = item["source_listing_id"]
            seen_ids.add(listing_id)

            existing = db.query(Listing).filter(
                Listing.source_listing_id == listing_id
            ).first()

            if existing:
                existing.ask_price = item["ask_price"]
                existing.status = ListingStatus.ACTIVE
                existing.fetched_at = datetime.utcnow()
                existing.last_seen_at = datetime.utcnow()
            else:
                listing = Listing(
                    complex_id=complex_id,
                    source_listing_id=listing_id,
                    ask_price=item["ask_price"],
                    exclusive_m2=item.get("exclusive_m2"),
                    floor=item.get("floor"),
                    status=ListingStatus.ACTIVE,
                    posted_at=item.get("posted_at"),
                    source="kb",
                    fetched_at=datetime.utcnow(),
                    last_seen_at=datetime.utcnow(),
                )
                db.add(listing)
            saved_count += 1

        # 이번에 안 보인 기존 ACTIVE 매물 → REMOVED
        if seen_ids:
            stale_listings = db.query(Listing).filter(
                Listing.complex_id == complex_id,
                Listing.status == ListingStatus.ACTIVE,
                Listing.source_listing_id.notin_(seen_ids),
            ).all()
            for stale in stale_listings:
                stale.status = ListingStatus.REMOVED
                stale.status_updated_at = datetime.utcnow()

        db.commit()
        task_record.status = TaskStatus.SUCCESS
        task_record.items_collected = len(result["items"])
        task_record.items_saved = saved_count
        logger.info(f"Task {task_key} completed: {len(result['items'])} items")
        return {"status": "success", "items_collected": len(result["items"])}

    except BaseException as e:
        logger.exception(f"Task {task_key} failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        task_record.status = TaskStatus.FAILED
        task_record.error_type = type(e).__name__
        task_record.error_message = str(e)[:500]
        return {"status": "failed", "error": str(e)}

    finally:
        task_record.finished_at = datetime.utcnow()
        try:
            db.commit()
        except Exception:
            pass
        _finalize_run_if_complete(db, run_id)


# =============================================================================
# KB 통합 수집 (시세 + 최근실거래가)
# =============================================================================

@celery_app.task(base=DatabaseTask, bind=True)
def run_kb_collection(
    self, job_id: int = None, run_id: int = None, target_config: str = None,
) -> Dict[str, Any]:
    """
    KB 데이터 통합 수집.
    각 단지마다 시세(면적별) 수집 — BasePrcInfoNew에서 시세 + 최근실거래가 동시 추출.
    """
    db = self.db

    if run_id:
        run = db.query(CrawlRun).filter(CrawlRun.id == run_id).first()
        run.status = RunStatus.RUNNING
        run.started_at = datetime.utcnow()
    else:
        run = CrawlRun(
            job_id=job_id,
            status=RunStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        db.add(run)
    db.commit()

    # target_config가 없으면 job에서 가져오기
    if not target_config and job_id:
        from models import CrawlJob
        j = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
        if j:
            target_config = j.target_config

    try:
        complexes = _get_target_complexes(db, target_config)

        total_tasks = 0
        for complex_obj in complexes:
            # 면적이 없으면 KB API에서 자동 조회
            areas = complex_obj.areas or ensure_complex_areas(db, complex_obj)

            # 시세 (면적별) — BasePrcInfoNew에서 시세 + 최근실거래가 동시 추출
            for area in areas:
                collect_kb_price_task.delay(
                    run_id=run.id,
                    complex_id=complex_obj.id,
                    area_id=area.id,
                )
                total_tasks += 1

            # 매물 수집 (단지별)
            collect_kb_listing_task.delay(
                run_id=run.id,
                complex_id=complex_obj.id,
            )
            total_tasks += 1

        db.commit()
        run.total_tasks = total_tasks
        db.commit()

        logger.info(f"Run {run.id}: Launched {total_tasks} tasks for {len(complexes)} complexes")
        return {"run_id": run.id, "total_tasks": total_tasks, "complexes_count": len(complexes)}

    except Exception as e:
        logger.exception(f"Run {run.id} failed: {e}")
        run.status = RunStatus.FAILED
        run.finished_at = datetime.utcnow()
        db.commit()
        raise


# =============================================================================
# 지역 기반 단지 발견 / 전체 수집
# =============================================================================

@celery_app.task(base=DatabaseTask, bind=True)
def discover_complexes_task(self, region_code: str) -> Dict[str, Any]:
    """지역코드로 아파트 단지 자동 발견 및 DB 등록"""
    from services.complex_discovery import ComplexDiscoveryService

    db = self.db
    service = ComplexDiscoveryService(db)
    result = run_async(service.discover_complexes(region_code))

    logger.info(
        f"Discovery for region {region_code}: "
        f"{result['new_registered']} new, {result['already_exists']} existing"
    )
    return result


@celery_app.task(base=DatabaseTask, bind=True)
def run_region_collection(
    self,
    region_code: str,
    job_id: int = None,
    run_id: int = None,
) -> Dict[str, Any]:
    """
    지역 기반 전체 수집:
    1. 단지 발견 (미등록 단지 자동 추가)
    2. 시세 수집 (단지별/면적별) — BasePrcInfoNew에서 시세 + 최근실거래가 동시 추출
    """
    db = self.db

    # 기존 run 사용 또는 신규 생성
    if run_id:
        run = db.query(CrawlRun).filter(CrawlRun.id == run_id).first()
        run.status = RunStatus.RUNNING
    else:
        run = CrawlRun(
            job_id=job_id,
            status=RunStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        db.add(run)
    db.commit()

    # Step 1: 단지 발견
    from services.complex_discovery import ComplexDiscoveryService
    service = ComplexDiscoveryService(db)
    discovery_result = run_async(service.discover_complexes(region_code))

    # Step 2: 해당 지역 활성 단지 조회
    region_prefix = region_code[:5] if len(region_code) >= 5 else region_code
    complexes = db.query(Complex).filter(
        Complex.region_code.like(f"{region_prefix}%"),
        Complex.is_active == True,
    ).all()

    if not complexes:
        logger.warning(f"No active complexes found for region {region_code}")
        run.status = RunStatus.SUCCESS
        run.finished_at = datetime.utcnow()
        db.commit()
        return {
            "region_code": region_code,
            "discovery": discovery_result,
            "run_id": run.id,
            "total_tasks": 0,
        }

    # Step 3: 태스크 실행
    total_tasks = 0
    for complex_obj in complexes:
        # 면적이 없으면 KB API에서 자동 조회
        areas = complex_obj.areas or ensure_complex_areas(db, complex_obj)

        for area in areas:
            collect_kb_price_task.delay(
                run_id=run.id,
                complex_id=complex_obj.id,
                area_id=area.id,
            )
            total_tasks += 1

        # 매물 수집 (단지별)
        collect_kb_listing_task.delay(
            run_id=run.id,
            complex_id=complex_obj.id,
        )
        total_tasks += 1

    run.total_tasks = total_tasks
    db.commit()

    logger.info(
        f"Region collection for {region_code}: "
        f"{len(complexes)} complexes, {total_tasks} tasks launched"
    )
    return {
        "region_code": region_code,
        "discovery": discovery_result,
        "run_id": run.id,
        "total_tasks": total_tasks,
        "complexes_count": len(complexes),
    }
