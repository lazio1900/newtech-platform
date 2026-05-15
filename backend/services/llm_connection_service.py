"""LLM 연결 관리 — admin panel 에서 사용.

- CRUD
- 기본(default) 연결 1개 보장
- 테스트 호출 (간단한 ping completion)
"""
from typing import Optional

from sqlalchemy.orm import Session

from models import LlmConnection


def list_connections(db: Session) -> list[LlmConnection]:
    return db.query(LlmConnection).order_by(LlmConnection.id.asc()).all()


def get_connection(db: Session, conn_id: int) -> Optional[LlmConnection]:
    return db.query(LlmConnection).filter(LlmConnection.id == conn_id).first()


def get_default_connection(db: Session) -> Optional[LlmConnection]:
    """LLMClient 가 사용하는 기본 연결. 없으면 None."""
    return (
        db.query(LlmConnection)
        .filter(LlmConnection.is_default == True, LlmConnection.is_active == True)  # noqa: E712
        .first()
    )


def create_connection(
    db: Session,
    *,
    name: str,
    provider: str,
    base_url: Optional[str],
    api_key: Optional[str],
    default_model: str,
    is_active: bool = True,
    set_default: bool = False,
) -> LlmConnection:
    conn = LlmConnection(
        name=name.strip(),
        provider=provider,
        base_url=(base_url or None),
        api_key=(api_key or None),
        default_model=default_model.strip(),
        is_active=is_active,
        is_default=False,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    if set_default:
        set_default_connection(db, conn.id)
        db.refresh(conn)
    return conn


def update_connection(
    db: Session,
    conn: LlmConnection,
    *,
    name: Optional[str] = None,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    default_model: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> LlmConnection:
    if name is not None:
        conn.name = name.strip()
    if provider is not None:
        conn.provider = provider
    if base_url is not None:
        conn.base_url = base_url or None
    if api_key is not None:
        # 빈 문자열 입력은 "변경 안 함" 으로 해석. None 으로 지우려면 명시 처리.
        if api_key.strip():
            conn.api_key = api_key.strip()
    if default_model is not None:
        conn.default_model = default_model.strip()
    if is_active is not None:
        conn.is_active = is_active
    db.commit()
    db.refresh(conn)
    return conn


def set_default_connection(db: Session, conn_id: int) -> Optional[LlmConnection]:
    """지정된 conn_id 를 default 로 — 나머지는 모두 false 로 만듦."""
    target = get_connection(db, conn_id)
    if not target:
        return None
    # 모든 connection 의 is_default 를 false 로
    db.query(LlmConnection).update({LlmConnection.is_default: False})
    target.is_default = True
    db.commit()
    db.refresh(target)
    return target


def delete_connection(db: Session, conn: LlmConnection) -> None:
    db.delete(conn)
    db.commit()


def test_connection(conn: LlmConnection) -> dict:
    """간단한 ping. OpenAI 호환 chat.completions 1회 호출 시도.

    성공 시 {'ok': True, 'model': ..., 'latency_ms': ...}
    실패 시 {'ok': False, 'error': '...'}
    """
    import time
    try:
        from openai import OpenAI
    except ImportError:
        return {"ok": False, "error": "openai SDK 미설치"}

    if not conn.api_key:
        return {"ok": False, "error": "API key 가 비어있습니다."}

    client_kwargs: dict = {"api_key": conn.api_key}
    if conn.base_url:
        client_kwargs["base_url"] = conn.base_url
    client = OpenAI(**client_kwargs)

    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=conn.default_model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}"}
    latency_ms = int((time.time() - t0) * 1000)
    return {
        "ok": True,
        "model": getattr(resp, "model", conn.default_model),
        "latency_ms": latency_ms,
    }
