"""정보계 Oracle ↔ PG 미러 매핑 — #1 운영 ETL(oracle_to_pg_etl) 과 시뮬레이터(oracle_sim_setup) 공용.

PG 내부형식 모델(internal_kb/registry_nice) ↔ Oracle 물리 테이블명(사내 명세 기준).
운영 실제 물리명/컬럼이 다르면 **여기(TABLE_MAP)와 컬럼만 조정**하면 ETL 본체는 불변.
"""
from sqlalchemy import BigInteger, Float, Integer, String, Text

from models import internal_kb as ik
from models import registry_nice as rn

# (PG 모델, Oracle 물리 테이블명). 등기부 Oracle 명은 주제명역 02.심사승인(CUWT_NIC_RLES_*).
TABLE_MAP = [
    (ik.CctrKbAptM, "CCTR_KB_APT_M"),
    (ik.CctrKbAptPntpI, "CCTR_KB_APT_PNTP_I"),
    (ik.CctrKbAptQtnL, "CCTR_KB_APT_QTN_L"),
    (ik.CctrAptTxcsHist, "CCTR_APT_TXCS_HIST"),
    (ik.CctrKbAptStdngC, "CCTR_KB_APT_STDNG_C"),
    (ik.CctrKbAptTxcsMpngB, "CCTR_KB_APT_TXCS_MPNG_B"),
    (rn.NiceRlesBasic, "CUWT_NIC_RLES_CCRG_M"),
    (rn.NiceRlesBrief, "CUWT_NIC_RLES_BRF_I"),
    (rn.NiceRlesCollateral, "CUWT_NIC_RLES_COLL_I"),
    (rn.NiceRlesDetail, "CUWT_NIC_RLES_CCRG_D"),
    (rn.NiceRlesParty, "CUWT_NIC_RLES_PDL_I"),
    (rn.NiceRlesHeader, "CUWT_NIC_RLES_HDR_D"),
]


def mirror_columns(model) -> list[str]:
    """미러 대상 PG 컬럼명 — surrogate 'id'(Oracle 자연키엔 없음) 제외."""
    return [c.name for c in model.__table__.columns if c.name != "id"]


def oracle_type(col) -> str:
    """SQLAlchemy 컬럼 → Oracle DDL 타입. BigInteger 가 Integer 하위라 먼저 분기."""
    t = col.type
    if isinstance(t, String):
        # CHAR 시맨틱 — PG 는 문자수 기준이라 한글(멀티바이트) 값이 BYTE 기준 VARCHAR2 를 넘는 것 방지
        return f"VARCHAR2({t.length or 2000} CHAR)"
    if isinstance(t, BigInteger):
        return "NUMBER(19)"
    if isinstance(t, Integer):
        return "NUMBER(10)"
    if isinstance(t, Float):
        return "BINARY_DOUBLE"
    if isinstance(t, Text):
        return "CLOB"
    return "VARCHAR2(4000)"


def connect_oracle():
    """oracledb thin connect — settings.oracle_dsn/user/password. 운영선 이 값만 사내로 교체."""
    import oracledb
    oracledb.defaults.fetch_lobs = False  # CLOB → str 로 직접 fetch (미러 매핑 단순화)

    from core.config import settings
    if not settings.oracle_dsn or not settings.oracle_user:
        raise RuntimeError("ORACLE_DSN/ORACLE_USER 미설정 — .env 에 정보계 접속정보 필요.")
    return oracledb.connect(
        user=settings.oracle_user,
        password=settings.oracle_password or "",
        dsn=settings.oracle_dsn,
    )
