"""INTERNAL_ONLY 사후 모니터링 — 앱 monitoring_loans 대신 정보계 6테이블에서 행 구성.

octr_loan_m(대출) ⨝ octr_loan_cmdt_m(물건) ⨝ opdm_rles_gd_d(부동산상세)
⨝ opdm_gd_adrgrd_m(주소) ⨝ ocst_cust_m(고객) → MonitoringLoan.to_dict() 와 동일 계약(dict).

식별 브리지: 정보계엔 app complex_id 가 없으므로 KB코드(kb_qtn_rles_gd_cd)로 complexes.id 를,
KB평형(kb_qtn_pntp_seqno)으로 areas.id 를 해소한다(상세팝업 분석 연동 — perform_full_analysis).
금액 단위: 정보계는 원(BigInteger). LTV = (선순위 + 당사대출) / 시세 × 100 (신청/심사 LTV 와 동일 기준).
담당자명은 직원마스터 부재라 여신담당직원번호(lnbz_chrg_empno)를 그대로 표기(placeholder).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from models.complex import Area, Complex
from models.internal_loan import (
    OcstCustM,
    OctrLoanCmdtM,
    OctrLoanM,
    OpdmGdAdrgrdM,
    OpdmRlesGdD,
)


def _fmt_date(yyyymmdd: Optional[str]) -> Optional[str]:
    if not yyyymmdd or len(yyyymmdd) < 8:
        return None
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"


def _ltv(exposure: int, price: Optional[int]) -> float:
    if not price:
        return 0.0
    return round(exposure / price * 100, 1)


def _signal(change: float) -> str:
    if change <= 0:
        return "green"
    if change <= 3.0:
        return "yellow"
    return "red"


_SIGNAL_LABEL = {"green": "안전", "yellow": "주의", "red": "위험"}


def _resolve_app_ids(
    db: Session, kb_complex_id: Optional[str], kb_pntp_seqno: Optional[int]
) -> tuple[Optional[int], Optional[int]]:
    """KB코드 → app-schema complex_id/area_id (상세 분석 연동용). 미매칭이면 (None, None)."""
    if not kb_complex_id:
        return None, None
    complex_obj = (
        db.query(Complex.id).filter(Complex.kb_complex_id == kb_complex_id).first()
    )
    if not complex_obj:
        return None, None
    complex_id = complex_obj[0]
    area_id = None
    if kb_pntp_seqno is not None:
        area_obj = (
            db.query(Area.id)
            .filter(Area.complex_id == complex_id, Area.kb_area_code == str(kb_pntp_seqno))
            .first()
        )
        area_id = area_obj[0] if area_obj else None
    return complex_id, area_id


def _address(adr: Optional[OpdmGdAdrgrdM], apt_nm: Optional[str]) -> str:
    parts = []
    if adr:
        parts = [p for p in (adr.addrsi, adr.addr_gu, adr.addong) if p]
    if apt_nm:
        parts.append(apt_nm)
    return " ".join(parts)


def list_internal_monitoring(db: Session) -> list[dict]:
    """정보계 대출 원장 기준 모니터링 행 목록. 대출당 주물건(mngd_yn='Y') 1건."""
    loans = db.query(OctrLoanM).order_by(OctrLoanM.loan_dt.desc()).all()

    custs = {c.cstno: c for c in db.query(OcstCustM).all()}
    cmdts: dict[tuple[str, str], OctrLoanCmdtM] = {}
    for m in db.query(OctrLoanCmdtM).all():
        key = (m.loanno, m.loan_seqno)
        # 주물건 우선, 없으면 첫 물건
        if key not in cmdts or m.mngd_yn == "Y":
            cmdts[key] = m
    rles = {r.gd_no: r for r in db.query(OpdmRlesGdD).all()}
    adrs: dict[str, OpdmGdAdrgrdM] = {}
    for a in db.query(OpdmGdAdrgrdM).all():
        if a.gd_no not in adrs or (a.gd_adrgrd_seqno or 0) < (adrs[a.gd_no].gd_adrgrd_seqno or 0):
            adrs[a.gd_no] = a

    rows: list[dict] = []
    for loan in loans:
        cust = custs.get(loan.cstno)
        cmdt = cmdts.get((loan.loanno, loan.loan_seqno))
        r = rles.get(cmdt.gd_no) if cmdt else None
        adr = adrs.get(cmdt.gd_no) if cmdt else None

        loan_amount = loan.loan_pcpl or 0
        prior_claims = (r.pror_fcrg_tlam if r else 0) or 0
        exposure = prior_claims + loan_amount
        execution_price = (r.aply_prc or r.ivst_prc) if r else None
        current_price = (r.ivst_prc or r.aply_prc) if r else None

        complex_id, area_id = _resolve_app_ids(
            db, r.kb_qtn_rles_gd_cd if r else None, r.kb_qtn_pntp_seqno if r else None
        )

        execution_ltv = _ltv(exposure, execution_price)
        current_ltv = _ltv(exposure, current_price)
        ltv_change = round(current_ltv - execution_ltv, 1)
        signal = _signal(ltv_change)

        rows.append(
            {
                "loan_id": loan.loanno,
                "application_id": None,
                "auditor_name": loan.lnbz_chrg_empno or "-",
                "company_name": (cust.cust_nm if cust else "") or "",
                "ceo_name": (cust.txnv_rptv_nm or cust.cust_nm) if cust else None,
                "property_address": _address(adr, r.apt_nm if r else None),
                "complex_id": complex_id,
                "area_id": area_id,
                "loan_amount": loan_amount,
                "prior_claims": prior_claims,
                "execution_date": _fmt_date(loan.loan_dt),
                "execution_price": execution_price or 0,
                "current_price": current_price or 0,
                "execution_ltv": execution_ltv,
                "current_ltv": current_ltv,
                "ltv_change": ltv_change,
                "signal": signal,
                "signal_label": _SIGNAL_LABEL[signal],
                "last_evaluated_at": None,
                "reevaluable": complex_id is not None,
            }
        )
    return rows


def summary_from_rows(rows: list[dict]) -> dict:
    total = len(rows)
    if total == 0:
        return {
            "total_count": 0, "green_count": 0, "yellow_count": 0, "red_count": 0,
            "total_amount": 0, "avg_current_ltv": 0.0,
        }
    return {
        "total_count": total,
        "green_count": sum(1 for r in rows if r["signal"] == "green"),
        "yellow_count": sum(1 for r in rows if r["signal"] == "yellow"),
        "red_count": sum(1 for r in rows if r["signal"] == "red"),
        "total_amount": sum(r["loan_amount"] for r in rows),
        "avg_current_ltv": round(sum(r["current_ltv"] for r in rows) / total, 1),
    }
