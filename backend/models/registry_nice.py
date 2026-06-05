"""NICE 부동산 등기부 6테이블 read-only ORM 미러.

수집기 ETL이 정보계 Oracle → 앱 PG(kb_estate)로 적재한 현재상태 스냅샷을 앱이
read-only로 읽기 위한 모델. 앱은 이 테이블에 INSERT/UPDATE/마이그레이션을 만들지 않는다
(ADR-011, ADR-002 대칭). 적재·물리스키마는 수집기 소유.

⚠️ 물리 테이블/컬럼명은 step4(internal-migration-registry-spec.md §2·§3) 역산 기준의
**잠정값**. 실 DDL·공통코드 master 확정(step4 §8) 후 정정. `id`는 ETL이 부여하는 surrogate.
조인키 = `rles_unq_no`(부동산고유번호 14자리).

이 모듈은 `registry_db_service` 에서만 import 한다(앱 alembic autogenerate 대상에서 제외 —
수집기 소유라 앱이 마이그레이션을 만들면 안 됨).
"""
from sqlalchemy import BigInteger, Column, Integer, String, Text

from core.database import Base


class NiceRlesBasic(Base):
    """기본행 — 부동산고유번호별 현재상태 요약 + 조회시점/카운트."""

    __tablename__ = "nice_rles_basic"

    id = Column(Integer, primary_key=True)
    rles_unq_no = Column(String(14), index=True, nullable=False, comment="부동산고유번호 14자리")
    nice_msgm_no = Column(String(20), comment="전문관리번호")
    rles_dvcd = Column(String(4), comment="부동산구분 3=집합건물")
    iqry_dt = Column(String(8), comment="조회시점 YYYYMMDD (신선도)")
    seiz_ccnt = Column(Integer, comment="압류 건수")
    prsz_ccnt = Column(Integer, comment="가압류 건수")
    pvsl_ccnt = Column(Integer, comment="가처분 건수")
    auct_opng_ccnt = Column(Integer, comment="경매개시 건수")
    fxcl_ccnt = Column(Integer, comment="(근)저당 건수")


class NiceRlesBrief(Base):
    """요약명세 — 갑구 소유지분현황(현재 소유자)."""

    __tablename__ = "nice_rles_brief"

    id = Column(Integer, primary_key=True)
    rles_unq_no = Column(String(14), index=True, nullable=False)
    rgty_rank_no = Column(String(20), comment="순위번호")
    rgty_nmnr_nm = Column(String(200), comment="소유자명")
    rnno = Column(Text, comment="실명번호 (암호문 base64 — 마스킹 노출)")
    own_last_shrs_ctnt = Column(String(100), comment="지분 (예: 단독소유)")
    rsdn_addr = Column(Text, comment="거주지주소 (암호문)")


class NiceRlesCollateral(Base):
    """저당명세 — 을구 현재 유효 담보권(말소 제외)."""

    __tablename__ = "nice_rles_collateral"

    id = Column(Integer, primary_key=True)
    rles_unq_no = Column(String(14), index=True, nullable=False)
    rgty_rank_no = Column(String(20), comment="순위번호")
    rgty_prps_cd = Column(String(20), comment="등기목적 코드")
    rgty_prps_ctnt = Column(String(100), comment="등기목적 텍스트 (근저당권설정/전세권설정/...)")
    rgty_actc_dt = Column(String(8), comment="접수일 YYYYMMDD")
    rgty_actc_no = Column(String(40), comment="접수번호")
    pdl_amt = Column(BigInteger, comment="금액(원) — 계산용 숫자값")
    pdl_amt_ctnt = Column(String(100), comment="금액 텍스트 (예: 금66,000,000원)")
    rtp_nm = Column(String(200), comment="권리자명 (근저당권자 등)")
    trgt_ownr_nm = Column(String(200), comment="대상소유자명")


class NiceRlesDetail(Base):
    """상세 — 갑/을구 전체 등기사항(이력). 갑구 권리침해(압류류) 추출에 사용."""

    __tablename__ = "nice_rles_detail"

    id = Column(Integer, primary_key=True)
    rles_unq_no = Column(String(14), index=True, nullable=False)
    ccrg_dvcd = Column(String(4), comment="1=갑구 2=을구")
    rgty_rank_no = Column(String(20))
    rgty_prps_cd = Column(String(20))
    rgty_prps_ctnt = Column(String(100), comment="등기목적 (가압류/가처분/압류/경매개시 등)")
    rgty_actc_dt = Column(String(8))
    rgty_actc_no = Column(String(40))


class NiceRlesParty(Base):
    """당사자명세 — 등기별 당사자(소유자/채무자/권리자/거래가액)."""

    __tablename__ = "nice_rles_party"

    id = Column(Integer, primary_key=True)
    rles_unq_no = Column(String(14), index=True, nullable=False)
    ccrg_dvcd = Column(String(4))
    rles_pdl_dvcd = Column(String(4), comment="당사자구분 21=소유자 20=채무자 46=근저당권자 ...")
    pdl_nm = Column(String(200), comment="당사자명")
    pdl_amt = Column(BigInteger, comment="금액(거래가액 등)")
    pdl_addr = Column(Text, comment="당사자주소 (암호문)")


class NiceRlesHeader(Base):
    """표제부 — 1동건물/전유부분 속성(평문). 속성 1건 = 1행(hdr_dtl_cd + 내용)."""

    __tablename__ = "nice_rles_header"

    id = Column(Integer, primary_key=True)
    rles_unq_no = Column(String(14), index=True, nullable=False)
    hdr_dtl_cd = Column(String(8), comment="C11소재지번 C12도로명 E43호 E82/E83전유면적 ...")
    hdr_ctnt = Column(Text, comment="속성 내용 (평문)")
