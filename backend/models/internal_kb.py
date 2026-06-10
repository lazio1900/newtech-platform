"""KB 시세 사내 내부형식(CCTR_*) 6테이블 ORM — 내부망 Oracle 스키마(17.기준관리)와 동형.

이 모델의 역할은 등기부 `registry_nice` 와 다르다. **앱은 이 테이블을 읽지 않는다.**
앱의 KB 읽기경로는 그대로 app-schema(`complexes`/`kb_prices`/`areas`/`transactions`)다
(Architecture A). CCTR_* 는 그 app-schema 를 채우는 **내부형식 원천**이다.

- 개발(dev) 모드: 크롤 데이터(app-schema) → 이 PG 테이블로 정형화(`build_cctr_from_crawl.py`)
  → `cctr_to_app.py` 변환으로 app-schema 재구성. PG CCTR_* 가 Oracle 을 시뮬레이션한다.
- 운영(prod) 모드: 이 형태(컬럼명)가 곧 Oracle 물리 테이블. 수집기가 Oracle CCTR_* 를
  읽어 동일 변환으로 app-schema 적재(step2 사양). PG 미러는 두지 않는다.

따라서 변환 로직(`cctr_to_app`)은 dev/prod 공통이고, **읽는 원천(PG vs Oracle)만 다르다.**
이게 모드 전환의 핵심. 자세한 절차는 `docs/internal-migration-mode-switch-runbook.md`.

ADR-002 대칭: 수집기 소유 read-only. 앱 alembic autogenerate 에서 제외(env.py 제외 목록).
컬럼명은 step1/step2 명세 기준. ★일부(STDNG_C 동명 등)는 실 Oracle DDL 로 확정 필요(주석 표시).
"""
from sqlalchemy import BigInteger, Column, Float, Integer, String

from core.database import Base


class CctrKbAptM(Base):
    """단지 마스터 CCTR_KB_APT_M → complexes."""

    __tablename__ = "cctr_kb_apt_m"

    kb_qtn_rles_gd_cd = Column(String(50), primary_key=True, comment="KB단지코드 (앱 kb_complex_id, 모든 자식 조인 기준키)")
    apt_nm = Column(String(200), comment="단지명 → complexes.name")
    road_nm_bsic_addr = Column(String(500), comment="도로명기본주소 → road_address")
    kb_qtn_stdng_cd = Column(String(10), comment="법정동코드 10자리 → dong_code, region_code=앞5자")
    cmcn_ym = Column(String(8), comment="준공년월 YYYYMM → built_year(to_str)")
    tot_gen_cnt = Column(Integer, comment="총세대수 → total_households")
    tot_dong_cnt = Column(Integer, comment="총동수 → total_buildings")
    hscm_hgst_flr = Column(Integer, comment="단지최고층 → max_floor")
    prkn_tcnt = Column(Integer, comment="주차대수 → total_parking")
    apst_yncd = Column(String(10), comment="주상복합여부코드 (정보계 OCTR_KB_APT_M) → ComplexScores.is_mixed_use 배지")
    # 주소 조각(공백조인 → complexes.address). null 조각은 skip.
    cnp_nm = Column(String(50), comment="시도명")
    ccw_nm = Column(String(50), comment="시군구명")
    old_nm = Column(String(50), comment="구읍면동명")
    emd_nm = Column(String(50), comment="읍면동명")
    ri_nm = Column(String(50), comment="리명")
    stad_ctnt = Column(String(300), comment="상세주소내용")


class CctrKbAptPntpI(Base):
    """평형 CCTR_KB_APT_PNTP_I → areas."""

    __tablename__ = "cctr_kb_apt_pntp_i"

    kb_qtn_rles_gd_cd = Column(String(50), primary_key=True, comment="KB단지코드 (complex FK resolve)")
    pntp_seqno = Column(String(20), primary_key=True, comment="평형순번 → areas.kb_area_code")
    exuse_are = Column(Float, comment="전용면적㎡ → exclusive_m2 (pyeong 은 적재 시 파생)")
    pntp_are = Column(Float, comment="공급면적㎡ → supply_m2")


class CctrKbAptQtnL(Base):
    """KB시세 CCTR_KB_APT_QTN_L → kb_prices. 금액 단위 만원(적재 시 ×10000)."""

    __tablename__ = "cctr_kb_apt_qtn_l"

    kb_qtn_rles_gd_cd = Column(String(50), primary_key=True, comment="KB단지코드")
    pntp_seqno = Column(String(20), primary_key=True, comment="평형순번 (area FK resolve)")
    ivst_base_dt = Column(String(8), primary_key=True, comment="기준일자 YYYYMMDD → as_of_date")
    deal_gnrl_txcs = Column(BigInteger, comment="일반거래시세(만원) → general_price(중심값)")
    deal_mxpr = Column(BigInteger, comment="매매상한가(만원) → high_avg_price")
    deal_mnpr = Column(BigInteger, comment="매매하한가(만원) → low_avg_price")
    dw_ldng_dttm = Column(String(14), comment="DW적재일시 YYYYMMDDHHMMSS (증분 워터마크)")


class CctrAptTxcsHist(Base):
    """국토부 실거래 CCTR_APT_TXCS_HIST → transactions. 금액 단위 만원."""

    __tablename__ = "cctr_apt_txcs_hist"

    seqno = Column(String(30), primary_key=True, comment="실거래 일련번호 → source_id")
    tx_dt = Column(String(8), comment="거래일자 YYYYMMDD → contract_date")
    tx_amt = Column(BigInteger, comment="거래금액(만원) → price(×10000)")
    apt_are = Column(Float, comment="전용면적㎡ → exclusive_m2")
    rlvn_flr = Column(Integer, comment="해당층 → floor")
    kb_qtn_rles_gd_cd = Column(String(50), index=True, comment="KB단지코드 (공백 가능 → 크로스워크 보강)")
    apt_nm = Column(String(200), comment="단지명 (KBA 공백 시 크로스워크 매칭키)")
    last_procs_dt = Column(String(8), comment="최종처리일자 (실거래 증분 워터마크 — DW_LDNG_DTTM 없음)")
    last_procs_time = Column(String(6), comment="최종처리시각")


class CctrKbAptStdngC(Base):
    """법정동코드 마스터 CCTR_KB_APT_STDNG_C — 코드→동명. region/동명 해석용."""

    __tablename__ = "cctr_kb_apt_stdng_c"

    kb_qtn_stdng_cd = Column(String(10), primary_key=True, comment="법정동코드 10자리")
    stdng_nm = Column(String(200), comment="법정동명 → dong_name (★컬럼명 실 DDL 확인 필요)")


class CctrKbAptTxcsMpngB(Base):
    """KB↔실거래 단지명 크로스워크 CCTR_KB_APT_TXCS_MPNG_B — KBA 공백 실거래 보강."""

    __tablename__ = "cctr_kb_apt_txcs_mpng_b"

    kb_qtn_rles_gd_cd = Column(String(50), primary_key=True, comment="KB단지코드")
    apt_nm = Column(String(200), primary_key=True, comment="정규화 단지명 (→ KBA 룩업)")
