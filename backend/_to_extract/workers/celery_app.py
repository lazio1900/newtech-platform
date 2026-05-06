from celery import Celery
from core.config import settings

# Initialize Celery app
celery_app = Celery(
    "kb_estate_collector",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour
    task_soft_time_limit=3000,  # 50 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    'collect-kb-data-daily': {
        'task': 'workers.tasks.run_kb_collection',
        'schedule': 86400.0,  # Daily (24 hours)
    },
}

# Auto-discover tasks
celery_app.autodiscover_tasks(['workers'])


# Worker signal handlers for browser cleanup
from celery.signals import worker_shutdown
import logging

_logger = logging.getLogger(__name__)


@worker_shutdown.connect
def on_worker_shutdown(**kwargs):
    """워커 종료 시 브라우저 세션 정리"""
    import asyncio
    try:
        from browser.session_manager import BrowserSessionManager
        loop = asyncio.new_event_loop()
        loop.run_until_complete(BrowserSessionManager.shutdown())
        loop.close()
        _logger.info("Browser sessions cleaned up on worker shutdown")
    except Exception as e:
        _logger.warning(f"Browser cleanup on shutdown failed: {e}")
