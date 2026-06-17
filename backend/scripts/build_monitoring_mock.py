"""[dev feeder] 골든셋 → 사후 모니터링 정보계 6테이블(O접두사) 합성 적재.

목적: 등기부가 존재하는 골든 8건을 앵커로 차주(대부업체)+대출 레이어를 합성해
정보계 6테이블을 self-consistent 하게 채워(=dev feeder) MonitoringTab 읽기경로를
빌드·검증한다. 운영 전환 시 이 자리를 수집기 Oracle ETL 이 대체한다.

설계 단일 출처: `docs/internal-migration-monitoring-mock-spec.md` §3·§4·§5·§7.
패턴: `scripts/build_cctr_from_crawl.py`(crawl→CCTR_*).

안전: 수집기 소유 테이블(complexes/areas/kb_prices …)은 read-only(ADR-002).
drop/create 는 본 6테이블 __table__ 한정(Base.metadata.* 금지 — 타 테이블 보호).
dev 전용(`settings.is_production` 차단). DB URL 은 /tmp/mock_db_url.txt 명시 사용.
"""
import json
import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings  # noqa: E402
from models.internal_loan import (  # noqa: E402
    OcstCustM,
    OctrLoanCmdtM,
    OctrLoanM,
    OctrRgplLnRepayL,
    OpdmGdAdrgrdM,
    OpdmRlesGdD,
)

GOLDEN_JSON = "/tmp/mock_golden_records.json"
DB_URL_FILE = "/tmp/mock_db_url.txt"

# drop 역순(자식→부모), create 정순. Base.metadata.drop_all/create_all 금지.
TABLES = [
    OcstCustM.__table__,
    OctrLoanM.__table__,
    OctrLoanCmdtM.__table__,
    OpdmRlesGdD.__table__,
    OpdmGdAdrgrdM.__table__,
    OctrRgplLnRepayL.__table__,
]

CUST_PREFIX = ["대성", "한빛", "우리", "금성", "동방", "신라", "대한", "제일"]


def _ymd(iso):
    """ISO 'YYYY-MM-DD' → 'YYYYMMDD' (모델 String(8)). None→None."""
    return iso.replace("-", "") if iso else None


def _first_lien_holder(rec):
    liens = rec.get("prior_liens") or []
    return liens[0].get("권리자") if liens else None


def _loan_pcpl(rec):
    if rec.get("matched") and rec.get("kb_recent_price"):
        return max(10_000_000, round(rec["kb_recent_price"] * 0.6) - (rec.get("prior_total") or 0))
    return 30_000_000


def _current_ltv(rec, loan_pcpl):
    if rec.get("matched") and rec.get("kb_recent_price"):
        return round(((rec.get("prior_total") or 0) + loan_pcpl) / rec["kb_recent_price"] * 100, 2)
    return None


def main() -> None:
    assert not settings.is_production, "dev 전용 스크립트 (운영 차단)"

    recs = json.load(open(GOLDEN_JSON))
    url = open(DB_URL_FILE).read().strip()
    engine = create_engine(url)

    for t in reversed(TABLES):
        t.drop(engine, checkfirst=True)
    for t in TABLES:
        t.create(engine, checkfirst=True)

    counts = {t.name: 0 for t in TABLES}
    matched_n = 0

    with Session(engine) as db:
        for i, rec in enumerate(recs):
            matched = bool(rec.get("matched"))
            if matched:
                matched_n += 1
            addr = rec.get("addr") or {}
            holder = _first_lien_holder(rec)
            prior_total = rec.get("prior_total")
            recent = rec.get("kb_recent_price")
            loan_pcpl = _loan_pcpl(rec)

            cstno = f"GOLDEN{i:09d}"
            loanno = f"26{i:09d}"
            gd_no = f"GD{i:08d}"

            db.add(OcstCustM(
                cstno=cstno,
                cust_stcd="01",
                cust_tycd="2",
                cust_nm=f"{CUST_PREFIX[i]}대부(주)",
                txnv_rptv_nm=f"대표자{i + 1}",
            ))
            counts["ocst_cust_m"] += 1

            db.add(OctrLoanM(
                loanno=loanno,
                loan_seqno="01",
                cstno=cstno,
                loan_stcd="32",
                loan_last_yn="Y",
                gds_cd=f"L{i:03d}",
                loan_pcpl=loan_pcpl,
                loan_dt=f"202601{10 + i:02d}",
                expr_dt="20290115",
                lnbz_chrg_empno="MOCK0001",
            ))
            counts["octr_loan_m"] += 1

            db.add(OctrLoanCmdtM(
                loanno=loanno,
                loan_seqno="01",
                gd_no=gd_no,
                cmdt_cd=f"C{i:03d}",
                appc_amt=loan_pcpl,
                pror_setp_amt1=prior_total,
                pror_rtp_nm=holder,
                setp_amt=round(loan_pcpl * 1.2),
                rles_unq_no=rec.get("rles_unq_no"),
                mngd_yn="Y",
            ))
            counts["octr_loan_cmdt_m"] += 1

            ltv = _current_ltv(rec, loan_pcpl) if matched else None
            db.add(OpdmRlesGdD(
                gd_no=gd_no,
                ccrg_unq_no=rec.get("rles_unq_no"),
                apt_nm=rec.get("apt_nm"),
                exuse_are=rec.get("exclusive_m2"),
                kb_qtn_rles_gd_cd=(rec.get("kb_complex_id") if matched else None),
                kb_qtn_pntp_seqno=(int(rec["kb_area_code"]) if matched and rec.get("kb_area_code") else None),
                kb_qtn_stdng_cd=(rec.get("dong_code") or rec.get("kb_stdng_cd")),
                kb_qtn_ivst_base_dt=_ymd(rec.get("kb_base_date")),
                ivst_prc=(recent if matched else None),
                aply_prc=(recent if matched else None),
                pror_fcrg_tlam=prior_total,
                dbtr_nm=rec.get("owner_nm"),
                rl_ownr_nm=rec.get("owner_nm"),
                fmps_nm=holder,
                tot_gen_cnt=rec.get("total_households"),
                ltv=ltv,
                appc_ltv=ltv,
                oncm_bnd_hgst_amt_ltv=ltv,
            ))
            counts["opdm_rles_gd_d"] += 1

            db.add(OpdmGdAdrgrdM(
                gd_no=gd_no,
                gd_adrgrd_seqno=1,
                gd_adrgrd_dvcd="02",
                addrsi=addr.get("si"),
                addr_gu=addr.get("gu"),
                addong=addr.get("dong"),
                addr_dtad=addr.get("raw"),
                road_nm_addr_yn="N",
            ))
            counts["opdm_gd_adrgrd_m"] += 1

        db.commit()

    # ── §7 기준선 ──────────────────────────────────────────────
    print("=== §7 기준선 ===")
    print("[테이블별 적재 행수]")
    for t in TABLES:
        print(f"  {t.name}: {counts[t.name]} rows")

    print(f"[매칭] matched={matched_n} / unmatched={len(recs) - matched_n}")

    with engine.connect() as c:
        join_n = c.execute(text("""
            SELECT count(*)
            FROM octr_loan_m l
            JOIN octr_loan_cmdt_m m ON m.loanno = l.loanno AND m.loan_seqno = l.loan_seqno
            JOIN opdm_rles_gd_d g    ON g.gd_no = m.gd_no
            JOIN opdm_gd_adrgrd_m a  ON a.gd_no = g.gd_no
            JOIN ocst_cust_m cu      ON cu.cstno = l.cstno
        """)).scalar()
        print(f"[조인 완결] octr_loan_m⨝cmdt⨝rles_gd⨝adrgrd⨝cust = {join_n} (기대 8)")

        kb_ok = c.execute(text("""
            SELECT count(*)
            FROM opdm_rles_gd_d g
            JOIN complexes cx ON cx.kb_complex_id = g.kb_qtn_rles_gd_cd
            WHERE g.kb_qtn_rles_gd_cd IS NOT NULL
        """)).scalar()
        print(f"[KB코드 실존] opdm_rles_gd_d.kb_qtn_rles_gd_cd ∈ complexes.kb_complex_id = {kb_ok} (기대 6)")

    print("\n[샘플 LTV 표 (matched)]")
    print(f"  {'slug':<10} {'loan_pcpl':>14} {'prior_total':>14} {'kb_recent_price':>16} {'current_ltv':>12}")
    for rec in recs:
        if not rec.get("matched"):
            continue
        lp = _loan_pcpl(rec)
        print(f"  {rec['slug']:<10} {lp:>14,} {(rec.get('prior_total') or 0):>14,} "
              f"{(rec.get('kb_recent_price') or 0):>16,} {str(_current_ltv(rec, lp)):>12}")

    print("\n[주의] PROR_FCRG_TLAM = 골든 을구 말소=false live 근저당 채권최고액 단순합 "
          "(spec §5) — chain 말소 미차감으로 과대계상 가능(garak ≈ 18.6억).")


if __name__ == "__main__":
    main()
