"""[dev feeder] 크롤 데이터(app-schema) → 내부형식 CCTR_* 6테이블 정형화.

목적: 폐쇄망 반입 전, 외부 크롤 데이터로 사내 내부형식(Oracle CCTR_* 와 동형) DB 를
만들어 `cctr_to_app.py` 변환을 검증한다. dev 모드 전용(운영/CI 금지).

방향: complexes/areas/kb_prices/transactions → cctr_kb_apt_m / _pntp_i / _qtn_l /
cctr_apt_txcs_hist (+ stdng_c 마스터, txcs_mpng_b 크로스워크). 단위 변환은 적재의 역:
앱은 원(BigInteger), CCTR_* 는 만원이므로 ÷10000. 주소는 STAD_CTNT 1조각에 전체를 넣어
역조합 시 동일 문자열 복원.

실행(컨테이너):
  docker compose exec backend python scripts/build_cctr_from_crawl.py --limit 300
  --limit  대상 단지 수(기본 300, 0=전체). 자식(평형/시세/실거래)은 그 단지들만.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings  # noqa: E402
from core.database import SessionLocal, engine  # noqa: E402
from models import internal_kb as ik  # noqa: E402
from models.complex import Area, Complex  # noqa: E402
from models.price_data import KBPrice, Transaction  # noqa: E402

_TABLES = [
    ik.CctrKbAptM, ik.CctrKbAptPntpI, ik.CctrKbAptQtnL,
    ik.CctrAptTxcsHist, ik.CctrKbAptStdngC, ik.CctrKbAptTxcsMpngB,
]


def _won_to_manwon(v):
    return round(v / 10000) if v is not None else None


def _ymd(d):
    return d.strftime("%Y%m%d") if d is not None else None


def _cmcn_ym(built_year):
    """'1984.06'/'198406'/'1984' → 'YYYYMM'(있는 만큼). 비면 None."""
    digits = "".join(c for c in (built_year or "") if c.isdigit())
    return digits[:6] or None


def _norm_name(name):
    return "".join((name or "").split())


def _synthetic_apst(kb):
    """dev 합성 주상복합여부 — 크롤엔 분류 없음. 정보계 APST_YNCD 는 T/F(샘플 준거).
    kb코드 해시로 ~20% 'T'(주상복합), 나머지 'F'. 운영은 OCTR_KB_APT_M.APST_YNCD 실값."""
    digits = "".join(c for c in (kb or "") if c.isdigit())
    return "T" if int(digits or "0") % 5 == 0 else "F"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=300, help="대상 단지 수 (0=전체)")
    ap.add_argument("--complex-ids", type=str, default="",
                    help="특정 app-schema 단지 id(쉼표) — append 모드(drop 안 함, 해당 단지만 갱신)")
    args = ap.parse_args()

    if settings.data_mode != "dev":
        print(f"거부: data_mode={settings.data_mode} (dev 전용 스크립트). 운영은 수집기 ETL.", file=sys.stderr)
        sys.exit(2)

    ids = [int(x) for x in args.complex_ids.split(",") if x.strip()]
    append = bool(ids)

    # dev 편의: 내부형식 테이블 재생성(per-table — 공유 ENUM 보호). append 모드는 drop 안 함.
    if not append:
        for t in _TABLES:
            t.__table__.drop(engine, checkfirst=True)
    for t in _TABLES:
        t.__table__.create(engine, checkfirst=True)

    db = SessionLocal()
    counts = {t.__tablename__: 0 for t in _TABLES}
    try:
        cq = db.query(Complex).filter(Complex.kb_complex_id.isnot(None))
        if ids:
            cq = cq.filter(Complex.id.in_(ids))
        cq = cq.order_by(Complex.id)
        if args.limit and not ids:
            cq = cq.limit(args.limit)
        complexes = cq.all()
        cplx_ids = [c.id for c in complexes]
        kba_of = {c.id: c.kb_complex_id for c in complexes}

        if append:
            # 대상 단지의 기존 CCTR 행 제거(PK 중복 방지). stdng_c 는 동코드 공유라 존재 시 skip.
            kbas = list(kba_of.values())
            for t in (ik.CctrKbAptM, ik.CctrKbAptPntpI, ik.CctrKbAptQtnL,
                      ik.CctrAptTxcsHist, ik.CctrKbAptTxcsMpngB):
                db.query(t).filter(t.kb_qtn_rles_gd_cd.in_(kbas)).delete(synchronize_session=False)

        # append: 이미 적재된 법정동코드는 재삽입 금지(PK 중복)
        stdng_seen = ({r[0] for r in db.query(ik.CctrKbAptStdngC.kb_qtn_stdng_cd).all()}
                      if append else set())
        mpng_seen = set()
        for c in complexes:
            db.add(ik.CctrKbAptM(
                kb_qtn_rles_gd_cd=c.kb_complex_id, apt_nm=c.name,
                road_nm_bsic_addr=c.road_address, kb_qtn_stdng_cd=c.dong_code,
                cmcn_ym=_cmcn_ym(c.built_year), tot_gen_cnt=c.total_households,
                tot_dong_cnt=c.total_buildings, hscm_hgst_flr=c.max_floor,
                prkn_tcnt=c.total_parking,
                apst_yncd=_synthetic_apst(c.kb_complex_id),  # dev 합성(크롤 원천 없음). 운영=OCTR 실값
                stad_ctnt=c.address,
            ))
            counts["cctr_kb_apt_m"] += 1
            if c.dong_code and c.dong_code not in stdng_seen:
                stdng_seen.add(c.dong_code)
                db.add(ik.CctrKbAptStdngC(kb_qtn_stdng_cd=c.dong_code, stdng_nm=c.dong_name))
                counts["cctr_kb_apt_stdng_c"] += 1
            mk = (c.kb_complex_id, _norm_name(c.name))
            if mk not in mpng_seen:
                mpng_seen.add(mk)
                db.add(ik.CctrKbAptTxcsMpngB(kb_qtn_rles_gd_cd=mk[0], apt_nm=mk[1]))
                counts["cctr_kb_apt_txcs_mpng_b"] += 1

        # 평형 — area_id → (KBA, pntp_seqno) 역참조 맵도 시세 적재에 사용.
        # pntp_seqno 는 복합 PK 컬럼 → NULL·단지내 중복 평형코드는 skip(quarantine).
        # 복도구조는 평형 단위(정보계 FRDR_STRC_CTNT)지만 크롤엔 단지단위(hallway_type)뿐 → 단지값 사용.
        hallway_of = {c.id: c.hallway_type for c in complexes}
        area_key = {}
        pntp_seen = set()
        skipped_area = 0
        for a in db.query(Area).filter(Area.complex_id.in_(cplx_ids)).all():
            kba = kba_of[a.complex_id]
            if not a.kb_area_code or (kba, a.kb_area_code) in pntp_seen:
                skipped_area += 1
                continue
            pntp_seen.add((kba, a.kb_area_code))
            db.add(ik.CctrKbAptPntpI(
                kb_qtn_rles_gd_cd=kba, pntp_seqno=a.kb_area_code,
                exuse_are=a.exclusive_m2, pntp_are=a.supply_m2,
                frdr_strc_ctnt=hallway_of.get(a.complex_id),
            ))
            counts["cctr_kb_apt_pntp_i"] += 1
            area_key[a.id] = (kba, a.kb_area_code)

        # KB시세 — (KBA, pntp_seqno, 기준일) PK 중복 방지(같은 면적·일자 1행).
        qtn_seen = set()
        for p in db.query(KBPrice).filter(KBPrice.complex_id.in_(cplx_ids)).all():
            key = area_key.get(p.area_id)
            if not key:
                continue
            pk = (key[0], key[1], _ymd(p.as_of_date))
            if pk in qtn_seen:
                continue
            qtn_seen.add(pk)
            db.add(ik.CctrKbAptQtnL(
                kb_qtn_rles_gd_cd=key[0], pntp_seqno=key[1], ivst_base_dt=pk[2],
                deal_gnrl_txcs=_won_to_manwon(p.general_price),
                deal_mxpr=_won_to_manwon(p.high_avg_price),
                deal_mnpr=_won_to_manwon(p.low_avg_price),
                dw_ldng_dttm=(p.fetched_at.strftime("%Y%m%d%H%M%S") if p.fetched_at else None),
            ))
            counts["cctr_kb_apt_qtn_l"] += 1

        # 실거래 — seqno PK. source_id 없거나 중복이면 SYN-{id}(별도 네임스페이스, 교차충돌 0).
        seq_seen = set()
        for t in db.query(Transaction).filter(Transaction.complex_id.in_(cplx_ids)).all():
            seqno = (t.source_id or "").strip() or f"SYN-{t.id}"
            if seqno in seq_seen:
                seqno = f"SYN-{t.id}"
            seq_seen.add(seqno)
            db.add(ik.CctrAptTxcsHist(
                seqno=seqno, tx_dt=_ymd(t.contract_date), tx_amt=_won_to_manwon(t.price),
                apt_are=t.exclusive_m2, rlvn_flr=t.floor,
                kb_qtn_rles_gd_cd=kba_of[t.complex_id], apt_nm=None,
                last_procs_dt=(t.fetched_at.strftime("%Y%m%d") if t.fetched_at else _ymd(t.contract_date)),
            ))
            counts["cctr_apt_txcs_hist"] += 1

        db.commit()
    finally:
        db.close()

    for t in _TABLES:
        print(f"  {t.__tablename__}: {counts[t.__tablename__]} rows")
    if skipped_area:
        print(f"  (평형 skip: {skipped_area} — NULL/중복 평형코드)")
    print(f"정형화 완료 (단지 {counts['cctr_kb_apt_m']}개 기준).")


if __name__ == "__main__":
    main()
