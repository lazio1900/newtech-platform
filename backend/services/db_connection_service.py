"""DB 연결 CRUD + 테스트.

테스트: psycopg2 로 SELECT 1 호출. 실제 backend 가 사용하는 connection 과 별개로
admin 입력 정보만으로 일회성 연결 시도.
"""
import time
from typing import Optional

from sqlalchemy.orm import Session

from models import DbConnection


def list_connections(db: Session) -> list[DbConnection]:
    return db.query(DbConnection).order_by(DbConnection.id.asc()).all()


def get_connection(db: Session, conn_id: int) -> Optional[DbConnection]:
    return db.query(DbConnection).filter(DbConnection.id == conn_id).first()


def create_connection(
    db: Session,
    *,
    name: str,
    driver: str,
    host: str,
    port: int,
    database: str,
    username: str,
    password: Optional[str],
    is_active: bool = True,
    set_default: bool = False,
) -> DbConnection:
    conn = DbConnection(
        name=name.strip(),
        driver=driver,
        host=host.strip(),
        port=port,
        database=database.strip(),
        username=username.strip(),
        password=(password or None),
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
    conn: DbConnection,
    *,
    name: Optional[str] = None,
    driver: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    database: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> DbConnection:
    if name is not None:
        conn.name = name.strip()
    if driver is not None:
        conn.driver = driver
    if host is not None:
        conn.host = host.strip()
    if port is not None:
        conn.port = port
    if database is not None:
        conn.database = database.strip()
    if username is not None:
        conn.username = username.strip()
    if password is not None and password.strip():
        # 빈 문자열은 미변경
        conn.password = password.strip()
    if is_active is not None:
        conn.is_active = is_active
    db.commit()
    db.refresh(conn)
    return conn


def set_default_connection(db: Session, conn_id: int) -> Optional[DbConnection]:
    target = get_connection(db, conn_id)
    if not target:
        return None
    db.query(DbConnection).update({DbConnection.is_default: False})
    target.is_default = True
    db.commit()
    db.refresh(target)
    return target


def delete_connection(db: Session, conn: DbConnection) -> None:
    db.delete(conn)
    db.commit()


def test_connection(conn: DbConnection) -> dict:
    """SELECT 1 호출. 성공 시 latency, 실패 시 error.
    현재는 postgresql 만 지원.
    """
    if conn.driver != "postgresql":
        return {"ok": False, "error": f"지원하지 않는 driver: {conn.driver}"}

    try:
        import psycopg2
    except ImportError:
        return {"ok": False, "error": "psycopg2 미설치"}

    t0 = time.time()
    try:
        c = psycopg2.connect(
            host=conn.host,
            port=conn.port,
            dbname=conn.database,
            user=conn.username,
            password=conn.password or "",
            connect_timeout=5,
        )
        try:
            cur = c.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.close()
        finally:
            c.close()
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}"}
    return {"ok": True, "latency_ms": int((time.time() - t0) * 1000)}
