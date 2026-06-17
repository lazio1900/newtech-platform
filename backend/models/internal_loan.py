"""사내 정보계(O접두사) 대출/물건/고객 6테이블 ORM — 사후 모니터링 원천.

명세 테이블명은 C접두사(CCST_/CCTR_/CPDM_)지만 정보계(운영 DW)는 O접두사다.
물리 테이블명은 소문자 O접두사로 둔다(ocst_cust_m / octr_loan_m / octr_loan_cmdt_m /
opdm_rles_gd_d / opdm_gd_adrgrd_m / octr_rgpl_ln_repay_l).

`internal_kb` 와 대칭: 수집기 소유 read-only 원천이므로 앱 alembic autogenerate 에서
제외하고, 본 앱은 SQLAlchemy 모델만 동기화한다(ADR-002). create_all 로 함께 생성되도록
같은 Base 를 사용한다. 설계 맥락은 `docs/internal-migration-monitoring-mock-spec.md` §3.

컬럼은 화면/매핑에 쓰이는 것 중심으로 추렸다(명세 전 컬럼이 아니다). 타입은 명세의
데이터타입을 따른다 — NUMBER 에 소수점 있으면 Float, 없고 금액이면 BigInteger.
"""
from sqlalchemy import BigInteger, Column, Float, Integer, String, Text

from core.database import Base


class OcstCustM(Base):
    """고객기본 OCST_CUST_M (명세 CCST_CUST_M) — 차주/실명 고객."""

    __tablename__ = "ocst_cust_m"

    cstno = Column(String(16), primary_key=True, comment="고객번호")
    cust_stcd = Column(String(2), comment="고객상태코드")
    cust_tycd = Column(String(1), comment="고객유형코드")
    cust_nm = Column(String(100), comment="고객명")
    txnv_rptv_nm = Column(String(50), comment="세금계산서대표자명")
    idvd_cust_busi_yn = Column(String(1), comment="개인고객사업자여부")


class OctrLoanM(Base):
    """대출기본 OCTR_LOAN_M (명세 CCTR_LOAN_M) — 대출 계약 단위."""

    __tablename__ = "octr_loan_m"

    loanno = Column(String(11), primary_key=True, comment="대출번호")
    loan_seqno = Column(String(2), primary_key=True, comment="대출일련번호")
    cstno = Column(String(16), comment="고객번호 → OcstCustM FK")
    loan_stcd = Column(String(2), comment="대출상태코드")
    loan_last_yn = Column(String(1), comment="대출최종여부")
    gds_cd = Column(String(4), comment="상품코드")
    loan_pcpl = Column(BigInteger, comment="대출원금")
    loan_pcpl_bal = Column(BigInteger, comment="대출원금잔액")
    loan_dt = Column(String(8), comment="대출일자 YYYYMMDD")
    aprv_dt = Column(String(8), comment="승인일자 YYYYMMDD")
    expr_dt = Column(String(8), comment="만기일자 YYYYMMDD")
    loan_intrt = Column(Float, comment="대출이자율 (NUMBER 7,4)")
    lnbz_chrg_empno = Column(String(8), comment="여신담당직원번호")


class OctrLoanCmdtM(Base):
    """대출물건기본 OCTR_LOAN_CMDT_M (명세 CCTR_LOAN_CMDT_M) — 대출별 담보물건."""

    __tablename__ = "octr_loan_cmdt_m"

    loanno = Column(String(11), primary_key=True, comment="대출번호")
    loan_seqno = Column(String(2), primary_key=True, comment="대출일련번호")
    gd_no = Column(String(10), primary_key=True, comment="물건번호 → OpdmRlesGdD FK")
    cmdt_cd = Column(String(4), comment="물품코드")
    gd_prc = Column(BigInteger, comment="물건가격")
    appc_amt = Column(BigInteger, comment="신청금액")
    pror_setp_amt1 = Column(BigInteger, comment="선순위설정금액1")
    pror_setp_amt2 = Column(BigInteger, comment="선순위설정금액2")
    pror_loan_pcpl = Column(BigInteger, comment="선순위대출원금")
    pror_rtp_nm = Column(String(30), comment="선순위권리자명")
    setp_amt = Column(BigInteger, comment="설정금액")
    base_prc = Column(BigInteger, comment="기준가격")
    rles_unq_no = Column(String(14), comment="부동산고유번호")
    mngd_yn = Column(String(1), comment="주물건여부")


class OpdmRlesGdD(Base):
    """부동산물건상세 OPDM_RLES_GD_D (명세 CPDM_RLES_GD_D) — 물건별 시세/권리/LTV."""

    __tablename__ = "opdm_rles_gd_d"

    gd_no = Column(String(10), primary_key=True, comment="물건번호")
    rles_gd_dvcd = Column(String(4), comment="부동산물건구분코드")
    ccrg_unq_no = Column(String(50), comment="등기부등본고유번호")
    apt_nm = Column(String(100), comment="아파트명")
    exuse_are = Column(Float, comment="전용면적㎡")
    are = Column(Float, comment="면적㎡")
    pntp_val = Column(String(10), comment="평형값")
    ltv = Column(Float, comment="LTV")
    appc_ltv = Column(Float, comment="신청LTV")
    oncm_bnd_hgst_amt_ltv = Column(Float, comment="당사채권최고금액LTV")
    brwr_bnd_hgst_amt_ltv = Column(Float, comment="차주채권최고금액LTV")
    lodb_guar_amt = Column(BigInteger, comment="전세보증금액")
    lent_guar_amt = Column(BigInteger, comment="임대보증금액")
    kb_qtn_rles_gd_cd = Column(String(9), comment="KB시세부동산물건코드")
    kb_qtn_pntp_seqno = Column(Integer, comment="KB시세평형일련번호")
    kb_qtn_stdng_cd = Column(String(10), comment="KB시세법정동코드")
    kb_qtn_ivst_base_dt = Column(String(8), comment="KB시세조사기준일자 YYYYMMDD")
    ivst_prc = Column(BigInteger, comment="조사가격")
    aply_prc = Column(BigInteger, comment="적용가격")
    avg_ivst_prc = Column(BigInteger, comment="평균조사가격")
    mih_ym = Column(String(6), comment="입주년월 YYYYMM")
    cmcn_dt = Column(String(8), comment="준공일자 YYYYMMDD")
    pror_fcrg_tlam = Column(BigInteger, comment="선순위근저당권총액")
    obnk_pror_fcrg_tlam = Column(BigInteger, comment="타행선순위근저당권총액")
    ojbb_pror_fcrg_tlam = Column(BigInteger, comment="당행선순위근저당권총액")
    oncm_exst_loan_amt = Column(BigInteger, comment="당사기존대출금액")
    dbtr_nm = Column(String(30), comment="채무자명")
    rl_ownr_nm = Column(String(100), comment="실소유자명")
    fmps_nm = Column(String(30), comment="근저당권자명")
    tot_gen_cnt = Column(Integer, comment="총세대수")
    seiz_ccnt = Column(String(3), comment="압류건수")
    rles_grad = Column(String(2), comment="부동산등급")


class OpdmGdAdrgrdM(Base):
    """물건주소지기본 OPDM_GD_ADRGRD_M (명세 CPDM_GD_ADRGRD_M) — 물건별 주소."""

    __tablename__ = "opdm_gd_adrgrd_m"

    gd_no = Column(String(10), primary_key=True, comment="물건번호 → OpdmRlesGdD FK")
    gd_adrgrd_seqno = Column(Integer, primary_key=True, comment="물건주소지일련번호")
    gd_adrgrd_dvcd = Column(String(2), comment="물건주소지구분코드")
    zpcd = Column(String(6), comment="우편번호")
    addrsi = Column(String(100), comment="주소시")
    addr_gu = Column(String(100), comment="주소구")
    addong = Column(String(100), comment="주소동")
    adroad = Column(String(100), comment="주소도로")
    addr_dtad = Column(Text, comment="주소상세주소")
    addr_dtad2 = Column(Text, comment="주소상세주소2")
    road_nm_addr_yn = Column(String(1), comment="도로명주소여부")


class OctrRgplLnRepayL(Base):
    """질권담보대출상환내역 OCTR_RGPL_LN_REPAY_L (명세 CCTR_RGPL_LN_REPAY_L)."""

    __tablename__ = "octr_rgpl_ln_repay_l"

    loanno = Column(String(11), primary_key=True, comment="대출번호")
    loan_seqno = Column(String(2), primary_key=True, comment="대출일련번호")
    gd_no = Column(String(10), primary_key=True, comment="물건번호")
    seqno = Column(BigInteger, primary_key=True, comment="일련번호")
    repay_dt = Column(String(8), comment="상환일자 YYYYMMDD")
    repay_amt = Column(BigInteger, comment="상환금액")
