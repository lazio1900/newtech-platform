"""IO-bound 병렬 실행 유틸 — LLM 호출처럼 대기 시간이 긴 작업용.

각 task 는 자체 SQLAlchemy 세션을 받는다 (SQLAlchemy 세션은 thread-safe 아님).
실패한 task 는 None 으로 반환하고 다른 task 진행에 영향 주지 않는다.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

TaskFn = Callable[[Session], Any]


def run_with_session(tasks: Dict[str, TaskFn], max_workers: int = 4) -> Dict[str, Any]:
    """병렬 실행. 각 task signature: (local_db: Session) -> Any. 실패는 None.

    호출 측에서 메인 세션의 ORM 객체를 그대로 넘기지 말 것 — 스칼라/dataclass 만
    캡처하고, 필요한 ORM 은 task 내부에서 local_db 로 다시 조회한다.
    """
    if not tasks:
        return {}

    from core.database import SessionLocal

    def _wrap(name: str, fn: TaskFn) -> Callable[[], Any]:
        def runner() -> Any:
            local_db = SessionLocal()
            try:
                return fn(local_db)
            except Exception as e:
                logger.warning(f"[parallel] {name} failed: {e}", exc_info=True)
                return None
            finally:
                local_db.close()

        return runner

    results: Dict[str, Any] = {name: None for name in tasks}
    workers = min(max_workers, len(tasks))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_wrap(n, fn)): n for n, fn in tasks.items()}
        for fut, name in futures.items():
            results[name] = fut.result()
    return results
