"""NICE 부동산 등기부 6테이블 read-only ORM 미러.

수집기 ETL이 정보계 Oracle → 앱 PG(kb_estate)로 적재한 현재상태 스냅샷을 앱이
read-only로 읽기 위한 모델. 앱은 이 테이블에 INSERT/UPDATE/마이그레이션을 만들지 않는다
(ADR-011, ADR-002 대칭). 적재·물리스키마는 수집기 소유.

컬럼명은 실제 명세(`etc/테이블/등기부등본/명세/*.xlsx`, CUWT_NIC_RLES_*)에 맞춤.
조인 키 계층: NICE_MSGM_NO(전문관리번호=1회 조회) → RLES_UNQ_NO(부동산고유번호 14자리)
→ CCRG_DVCD(1갑구/2을구) → CCRG_SEQNO. 한 물건이 여러 번 조회되면 NICE_MSGM_NO 가
여럿 — **최신 스냅샷(기본행 IQRY_DT 최대)의 NICE_MSGM_NO 로 자식 테이블을 조인**한다.
`id`는 ETL/로더가 부여하는 surrogate.

이 모듈은 `registry_db_service`/로더에서만 import 한다(앱 alembic autogenerate 제외 —
수집기 소유라 앱이 마이그레이션을 만들면 안 됨, ADR-011; env.py 제외 목록에도 명시).
"""
from sqlalchemy import BigInteger, Column, Integer, String, Text

from core.database import Base


class NiceRlesBasic(Base):
    """기본행 CUWT_NIC_RLES_CCRG_M — 부동산고유번호별 조회 스냅샷 + 카운트."""

    __tablename__ = "nice_rles_basic"

    id = Column(Integer, primary_key=True)
    nice_msgm_no = Column(String(20), index=True, comment="NICE전문관리번호 (조회 1건)")
    rles_unq_no = Column(String(14), index=True, nullable=False, comment="부동산고유번호 14자리")
    rles_dvcd = Column(String(2), comment="부동산구분 3=집합건물")
    lctn_addr = Column(Text, comment="소재지주소 (암호문 base64 — 사용 안 함, 주소는 표제부 평문)")
    stdng_cd = Column(String(10), comment="법정동코드")
    seiz_ccnt = Column(Integer, comment="압류 건수")
    prsz_ccnt = Column(Integer, comment="가압류 건수")
    pvsl_ccnt = Column(Integer, comment="가처분 건수")
    auct_opng_ccnt = Column(Integer, comment="경매개시 건수")
    fxcl_ccnt = Column(Integer, comment="근저당 건수")
    iqry_dt = Column(String(8), comment="조회일자 YYYYMMDD (신선도·최신 스냅샷 판정)")


class NiceRlesBrief(Base):
    """요약명세 CUWT_NIC_RLES_BRF_I — 갑구 소유지분현황(현재 소유자)."""

    __tablename__ = "nice_rles_brief"

    id = Column(Integer, primary_key=True)
    nice_msgm_no = Column(String(20), index=True)
    rles_unq_no = Column(String(14), index=True, nullable=False)
    ccrg_seqno = Column(Integer)
    rgty_rank_no = Column(String(10), comment="등기순위번호")
    rgty_nmnr_nm = Column(String(50), comment="등기명의인명(소유자)")
    ownr_cnps_ctnt = Column(String(20), comment="소유자관계자내용")
    rnno = Column(String(44), comment="실명번호 (암호문 base64 — 마스킹 노출, PII)")
    own_last_shrs_ctnt = Column(String(30), comment="소유최종지분내용 (예: 단독소유)")
    rsdn_addr = Column(Text, comment="거주지주소 (암호문)")


class NiceRlesCollateral(Base):
    """저당명세 CUWT_NIC_RLES_COLL_I — 을구 현재 유효 담보권(말소 제외)."""

    __tablename__ = "nice_rles_collateral"

    id = Column(Integer, primary_key=True)
    nice_msgm_no = Column(String(20), index=True)
    rles_unq_no = Column(String(14), index=True, nullable=False)
    ccrg_dvcd = Column(String(1), comment="1=갑구 2=을구")
    ccrg_seqno = Column(Integer)
    ccrg_coll_seqno = Column(BigInteger)
    rgty_rank_no = Column(String(10), comment="등기순위번호")
    rgty_prps_ctnt = Column(String(100), comment="등기목적 텍스트 (근저당권설정/전세권설정/질권/...)")
    rgty_prps_cd = Column(String(10), comment="등기목적코드 (C2313001=근저당권설정 C2100001=질권)")
    rgty_actc_dt = Column(String(8), comment="등기접수일자")
    rgty_actc_no = Column(String(12), comment="등기접수번호")
    trgt_ownr_nm = Column(String(30), comment="대상소유자명")
    rtp_nm = Column(String(100), comment="권리자명 (근저당권자 등)")
    pdl_amt_ctnt = Column(String(30), comment="당사자금액 텍스트 (예: 금66,000,000원)")
    pdl_amt = Column(BigInteger, comment="당사자금액(원) — 계산용 숫자값")


class NiceRlesDetail(Base):
    """상세 CUWT_NIC_RLES_CCRG_D — 갑/을구 전체 등기사항. 갑구 권리침해(압류류) 추출."""

    __tablename__ = "nice_rles_detail"

    id = Column(Integer, primary_key=True)
    nice_msgm_no = Column(String(20), index=True)
    rles_unq_no = Column(String(14), index=True, nullable=False)
    ccrg_dvcd = Column(String(1), comment="1=갑구 2=을구")
    ccrg_seqno = Column(Integer)
    ccrg_rank_no = Column(String(12), comment="등기부등본순위번호")
    rgty_prps_ctnt = Column(String(100), comment="등기목적 (가압류/가처분/압류/경매개시 등)")
    rgty_actc_dt = Column(String(8))
    rgty_actc_no = Column(String(12))
    rgty_caus_ctnt = Column(String(255), comment="등기원인내용")
    brf_part_ofr_yn = Column(String(1), comment="요약부분제공여부")


class NiceRlesParty(Base):
    """당사자명세 CUWT_NIC_RLES_PDL_I — 등기별 당사자(소유자/채무자/권리자/거래가액)."""

    __tablename__ = "nice_rles_party"

    id = Column(Integer, primary_key=True)
    nice_msgm_no = Column(String(20), index=True)
    rles_unq_no = Column(String(14), index=True, nullable=False)
    ccrg_dvcd = Column(String(1))
    ccrg_seqno = Column(Integer)
    ccrg_rank_no = Column(String(12))
    rles_pdl_dvcd = Column(String(2), comment="당사자구분 21소유자 20채무자 46근저당권자 42전세권자 10질권채권자")
    pdl_nm = Column(String(100), comment="당사자명")
    rnno = Column(String(44), comment="실명번호 (암호문, PII)")
    pdl_amt = Column(BigInteger, comment="당사자금액(거래가액 등)")
    pdl_addr = Column(Text, comment="당사자주소 (암호문)")


class NiceRlesHeader(Base):
    """표제부 CUWT_NIC_RLES_HDR_D — 1동건물/전유부분 속성(평문). 속성 1건 = 1행(hdr_dtl_cd + 내용).

    HDR_CTNT 는 명세상 NUMBER 이나 실제는 텍스트(주소·층·호 등) — 로더가 문자열로 적재.
    """

    __tablename__ = "nice_rles_header"

    id = Column(Integer, primary_key=True)
    nice_msgm_no = Column(String(20), index=True)
    rles_unq_no = Column(String(14), index=True, nullable=False)
    ccrg_seqno = Column(Integer)
    ccrg_rank_no = Column(String(12))
    hdr_dtl_cd = Column(String(5), comment="C11소재지번 C12도로명 E43호 E82전유면적 C87용도 ...")
    hdr_ctnt = Column(Text, comment="속성 내용 (평문 텍스트)")
