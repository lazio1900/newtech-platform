"""등기부 PDF → 6테이블(nice_rles_*) 재구성 로더 (외부 테스트/브리지).

PDF → MinerU markdown → LLM 추출(ai_rights_analysis_service.extract_rights_dict, critique 포함)
→ dict 를 nice_rles_* 행으로 explode → 적재. 이후 registry_db_service 가 결정적으로 빌드.

NICE DB(정확값) 와 달리 PDF→LLM 은 추출 오차가 있는 *테스트/브리지* 경로다. 구조 키
(NICE_MSGM_NO/CCRG_SEQNO/코드)는 합성한다 — 빌더가 쓰는 건 텍스트 필드(purpose·금액·이름·주소)뿐.

실행(컨테이너 권장 — MinerU 8200·LLM 도달):
  docker compose cp <pdf> backend:/tmp/r.pdf
  docker compose exec backend python scripts/load_pdf_as_nice.py /tmp/r.pdf [부동산고유번호]
부동산고유번호 생략 시 파일명의 NNNN-NNNN-NNNNNN 패턴에서 추출.
"""
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings  # noqa: E402
from core.database import SessionLocal, engine  # noqa: E402
from models import registry_nice as rn  # noqa: E402
from services.ai_rights_analysis_service import (  # noqa: E402
    _extract_markdown,
    extract_rights_dict,
)

_UNQ_IN_NAME = re.compile(r"(\d{4}-\d{4}-\d{6})")
_UNQ_LABELED = re.compile(r"고유번호[\s:]*([0-9]{4}[-\s]?[0-9]{4}[-\s]?[0-9]{6})")
_AMOUNT = re.compile(r"([\d,]+)\s*원")
_TABLES = [
    rn.NiceRlesBasic, rn.NiceRlesBrief, rn.NiceRlesCollateral,
    rn.NiceRlesDetail, rn.NiceRlesParty, rn.NiceRlesHeader,
]


def _digits(s: str) -> str:
    return "".join(c for c in (s or "") if c.isdigit())


def _unq_from_text(text: str) -> str:
    """등기부 본문에서 부동산고유번호 추출 — '고유번호 NNNN-NNNN-NNNNNN' 우선, 없으면 첫 패턴."""
    m = _UNQ_LABELED.search(text or "") or _UNQ_IN_NAME.search(text or "")
    return _digits(m.group(1)) if m else ""


_EXCL_M2 = re.compile(r"([0-9]+\.[0-9]+)\s*(?:m2|㎡|m²)")


def _exclusive_m2_from_text(text: str):
    """표제부 '전유부분의 건물의 표시' 섹션의 첫 면적(전유면적) — 평형 자동선택용. 없으면 None."""
    idx = (text or "").find("전유부분의 건물의 표시")
    if idx < 0:
        return None
    m = _EXCL_M2.search(text[idx:idx + 600])
    return m.group(1) if m else None


def _amount(text: str) -> int:
    m = _AMOUNT.search(text or "")
    if not m:
        return 0
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return 0


def _count_kw(entries, *kws) -> int:
    return sum(1 for e in entries if any(k in (e.get("purpose") or "") for k in kws))


def explode(d: dict, unq: str, today: str, exclusive_m2: str | None = None) -> list:
    """추출 dict → nice_rles_* ORM 인스턴스 목록. NICE_MSGM_NO 등 구조키는 합성."""
    msgm = ("PDF" + unq)[:20]
    rows: list = []

    mortgages = d.get("mortgage_entries") or []
    gap_other = d.get("ownership_other_entries") or []
    owners = d.get("ownership_entries") or []

    rows.append(rn.NiceRlesBasic(
        nice_msgm_no=msgm, rles_unq_no=unq, rles_dvcd="3", iqry_dt=today,
        seiz_ccnt=_count_kw(gap_other, "압류") - _count_kw(gap_other, "가압류"),
        prsz_ccnt=_count_kw(gap_other, "가압류"),
        pvsl_ccnt=_count_kw(gap_other, "가처분"),
        auct_opng_ccnt=_count_kw(gap_other, "경매"),
        fxcl_ccnt=_count_kw(mortgages, "근저당"),
    ))

    for o in owners:
        rows.append(rn.NiceRlesBrief(
            nice_msgm_no=msgm, rles_unq_no=unq,
            rgty_rank_no=str(o.get("rank_number") or ""),
            rgty_nmnr_nm=(o.get("name") or "")[:50],
            own_last_shrs_ctnt=(o.get("share") or "")[:30],
            rsdn_addr=o.get("address") or "",
        ))

    for m in mortgages:
        details = m.get("main_details") or ""
        rows.append(rn.NiceRlesCollateral(
            nice_msgm_no=msgm, rles_unq_no=unq, ccrg_dvcd="2",
            rgty_rank_no=str(m.get("rank_number") or ""),
            rgty_prps_ctnt=(m.get("purpose") or "")[:100],
            rgty_actc_dt=None, rgty_actc_no=None,
            trgt_ownr_nm=(m.get("target_owner") or "")[:30],
            pdl_amt_ctnt=details[:30], pdl_amt=_amount(details),
        ))

    for g in gap_other:
        rows.append(rn.NiceRlesDetail(
            nice_msgm_no=msgm, rles_unq_no=unq, ccrg_dvcd="1",
            ccrg_rank_no=str(g.get("rank_number") or ""),
            rgty_prps_ctnt=(g.get("purpose") or "")[:100],
            rgty_caus_ctnt=(g.get("details") or "")[:255],
        ))

    # 주소: 소유자 주소를 표제부 C12(도로명) 1행으로 — 빌더가 property 주소로 픽업.
    addr = next((o.get("address") for o in owners if o.get("address")), "")
    if addr:
        rows.append(rn.NiceRlesHeader(
            nice_msgm_no=msgm, rles_unq_no=unq, hdr_dtl_cd="C12", hdr_ctnt=addr,
        ))
    # 전유면적 E82 — 평형 자동선택용
    if exclusive_m2:
        rows.append(rn.NiceRlesHeader(
            nice_msgm_no=msgm, rles_unq_no=unq, hdr_dtl_cd="E82", hdr_ctnt=f"{exclusive_m2}㎡",
        ))
    return rows


def main() -> None:
    if settings.data_mode != "dev":
        print(f"거부: data_mode={settings.data_mode} (dev 전용 로더). "
              "운영은 수집기 Oracle 미러가 nice_rles_* 를 소유한다.", file=sys.stderr)
        sys.exit(2)
    if len(sys.argv) < 2:
        print("usage: load_pdf_as_nice.py <pdf> [부동산고유번호]", file=sys.stderr)
        sys.exit(1)
    pdf_path = sys.argv[1]
    unq = _digits(sys.argv[2]) if len(sys.argv) > 2 else ""
    if len(unq) != 14:
        mm = _UNQ_IN_NAME.search(os.path.basename(pdf_path))
        unq = _digits(mm.group(1)) if mm else ""

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    print(f"MinerU 변환 중... ({os.path.basename(pdf_path)}, {len(pdf_bytes)} bytes)")
    text = _extract_markdown(pdf_bytes)
    if not text.strip():
        print("MinerU markdown 비어있음 — 중단", file=sys.stderr)
        sys.exit(1)
    if len(unq) != 14:  # arg/파일명에 없으면 등기부 본문에서 추출
        unq = _unq_from_text(text)
    if len(unq) != 14:
        print("부동산고유번호 14자리를 arg/파일명/본문 어디서도 못 찾음 — 인자로 넘기세요.", file=sys.stderr)
        sys.exit(1)
    print(f"  고유번호 {unq} · markdown {len(text)}자 → LLM 추출")

    db = SessionLocal()
    try:
        d = extract_rights_dict(db, text, label=os.path.basename(pdf_path))
        rows = explode(d, unq, datetime.now().strftime("%Y%m%d"), _exclusive_m2_from_text(text))

        for t in _TABLES:
            t.__table__.create(engine, checkfirst=True)
            db.query(t).filter(t.rles_unq_no == unq).delete()
        for r in rows:
            db.add(r)
        db.commit()
    finally:
        db.close()

    print(f"적재 완료 (unq={unq}): "
          f"소유자 {len(d.get('ownership_entries') or [])} · "
          f"저당 {len(d.get('mortgage_entries') or [])} · "
          f"소유권외 {len(d.get('ownership_other_entries') or [])} · "
          f"LLM max_bond={int(d.get('max_bond_amount') or 0):,}")


if __name__ == "__main__":
    main()
