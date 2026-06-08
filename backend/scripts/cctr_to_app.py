"""내부형식 CCTR_* → app-schema 변환 (KB 내부 이관의 핵심 변환 — dev/prod 공통 로직).

이 변환이 모드 전환의 불변 핵심이다. **읽는 원천만 다르고 변환은 같다**:
- dev : 원천 = PG CCTR_*(`build_cctr_from_crawl` 가 만든 것). 이 스크립트로 실행.
- prod: 원천 = Oracle CCTR_*. 수집기가 동일 매핑으로 app-schema 적재(step2 사양).

단위/파생(field_mappings step1 기준): 금액 만원→원(×10000), 날짜 YYYYMMDD→date,
region_code=법정동코드[:5], pyeong=㎡/3.305785, 주소=6조각 공백조인.

  --verify (기본)  app-schema 기존행과 대조만(쓰기 없음). build 의 --limit 범위 내에서만
                   (전량 verify 는 메모리 큼 — --limit 0 비권장). 충실도 검증용.
  --apply          app-schema 로 멱등 upsert(dev 전용). 빈 app-schema 클린룸 적재 검증용.

실행: docker compose exec backend python scripts/cctr_to_app.py [--verify|--apply]
"""
import argparse
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings  # noqa: E402
from core.database import SessionLocal  # noqa: E402
from models import internal_kb as ik  # noqa: E402
from models.complex import Area, Complex  # noqa: E402
from models.price_data import KBPrice, Transaction  # noqa: E402

_M2PYEONG = 3.305785


def _won(manwon):
    return manwon * 10000 if manwon is not None else None


def _date(ymd):
    return date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8])) if ymd and len(ymd) == 8 else None


def _year(v):
    digits = "".join(c for c in str(v or "") if c.isdigit())
    return digits[:4] or None


def _compose_addr(m: ik.CctrKbAptM) -> str:
    parts = [m.cnp_nm, m.ccw_nm, m.old_nm, m.emd_nm, m.ri_nm, m.stad_ctnt]
    return " ".join(p.strip() for p in parts if p and p.strip())


def complex_fields(m: ik.CctrKbAptM, dong_name: str | None) -> dict:
    return {
        "kb_complex_id": m.kb_qtn_rles_gd_cd,
        "name": m.apt_nm,
        "road_address": m.road_nm_bsic_addr,
        "dong_code": m.kb_qtn_stdng_cd,
        "dong_name": dong_name,
        "region_code": (m.kb_qtn_stdng_cd or "")[:5] or None,
        "built_year": m.cmcn_ym,
        "total_households": m.tot_gen_cnt,
        "address": _compose_addr(m) or m.apt_nm,
    }


def area_fields(p: ik.CctrKbAptPntpI) -> dict:
    return {
        "kb_area_code": p.pntp_seqno,
        "exclusive_m2": p.exuse_are,
        "supply_m2": p.pntp_are,
        "pyeong": round(p.exuse_are / _M2PYEONG, 2) if p.exuse_are is not None else None,
    }


def price_fields(q: ik.CctrKbAptQtnL) -> dict:
    return {
        "as_of_date": _date(q.ivst_base_dt),
        "general_price": _won(q.deal_gnrl_txcs),
        "high_avg_price": _won(q.deal_mxpr),
        "low_avg_price": _won(q.deal_mnpr),
    }


def _verify(db) -> None:
    stdng = {s.kb_qtn_stdng_cd: s.stdng_nm for s in db.query(ik.CctrKbAptStdngC).all()}
    kbas = [r[0] for r in db.query(ik.CctrKbAptM.kb_qtn_rles_gd_cd).all()]
    m1 = {c.kb_complex_id: c
          for c in db.query(Complex).filter(Complex.kb_complex_id.in_(kbas)).all()}
    cids = [c.id for c in m1.values()]

    # complexes — region_code 는 내부형식에서 법정동코드[:5]로 derive(크롤 별도출처와 다를 수
    # 있고, 운영엔 derive 만 존재 → 정상 교정). 핵심필드 불일치와 분리 집계.
    ok = miss = mismatch = region_drift = 0
    samples = []
    for m in db.query(ik.CctrKbAptM).all():
        exist = m1.get(m.kb_qtn_rles_gd_cd)
        if not exist:
            miss += 1
            continue
        f = complex_fields(m, stdng.get(m.kb_qtn_stdng_cd))
        if (exist.region_code or "") != (f["region_code"] or ""):
            region_drift += 1
        diffs = []
        if (exist.name or "") != (f["name"] or ""):
            diffs.append("name")
        if " ".join((exist.address or "").split()) != " ".join((f["address"] or "").split()):
            diffs.append("address")
        if _year(exist.built_year) != _year(f["built_year"]):
            diffs.append("built_year")
        if (exist.total_households or 0) != (f["total_households"] or 0):
            diffs.append("total_households")
        if diffs:
            mismatch += 1
            if len(samples) < 5:
                samples.append(f"  KBA={m.kb_qtn_rles_gd_cd} 불일치 {diffs}")
        else:
            ok += 1
    print(f"complexes  핵심일치={ok} 핵심불일치={mismatch} app에없음={miss} "
          f"· region_code 교정(정상)={region_drift}")
    for s in samples:
        print(s)

    # kb_prices — 면적 룩업(complex_id, kb_area_code)→area_id, (complex_id, area_id, date)→price
    areas = {(a.complex_id, a.kb_area_code): a.id
             for a in db.query(Area).filter(Area.complex_id.in_(cids)).all()}
    pcache = {}
    for p in db.query(KBPrice).filter(KBPrice.complex_id.in_(cids)).all():
        pcache[(p.complex_id, p.area_id, p.as_of_date)] = p
    pok = pmiss = pmismatch = 0
    psamp = []
    for q in db.query(ik.CctrKbAptQtnL).all():
        c = m1.get(q.kb_qtn_rles_gd_cd)
        if not c:
            pmiss += 1
            continue
        aid = areas.get((c.id, q.pntp_seqno))
        f = price_fields(q)
        exist = pcache.get((c.id, aid, f["as_of_date"])) if aid else None
        if not exist:
            pmiss += 1
            continue
        diff_g = (exist.general_price or 0) != (f["general_price"] or 0)
        diff_h = (exist.high_avg_price or 0) != (f["high_avg_price"] or 0)
        diff_l = (exist.low_avg_price or 0) != (f["low_avg_price"] or 0)
        if diff_g or diff_h or diff_l:
            pmismatch += 1
            if len(psamp) < 5:
                which = "".join(c for c, d in [("g", diff_g), ("h", diff_h), ("l", diff_l)] if d)
                psamp.append(f"  KBA={q.kb_qtn_rles_gd_cd} {q.ivst_base_dt} 불일치[{which}] "
                             f"app(g={exist.general_price},h={exist.high_avg_price},l={exist.low_avg_price})")
        else:
            pok += 1
    print(f"kb_prices  일치={pok} 불일치(g/h/l)={pmismatch} app에없음={pmiss}")
    for s in psamp:
        print(s)

    # areas / transactions — 해소율만
    a_ok = sum(1 for p in db.query(ik.CctrKbAptPntpI).all()
               if (m1.get(p.kb_qtn_rles_gd_cd) and (m1[p.kb_qtn_rles_gd_cd].id, p.pntp_seqno) in areas))
    a_total = db.query(ik.CctrKbAptPntpI).count()
    print(f"areas      app매칭={a_ok}/{a_total}")
    t_total = db.query(ik.CctrAptTxcsHist).count()
    t_kba = db.query(ik.CctrAptTxcsHist).filter(ik.CctrAptTxcsHist.kb_qtn_rles_gd_cd.in_(list(m1.keys()))).count()
    print(f"txcs_hist  KBA해소={t_kba}/{t_total}")


def _apply(db) -> None:
    """dev 전용 멱등 upsert(SELECT-후-분기, dev 규모). 운영은 수집기 ETL."""
    now = datetime.utcnow()
    stdng = {s.kb_qtn_stdng_cd: s.stdng_nm for s in db.query(ik.CctrKbAptStdngC).all()}
    kbas = [r[0] for r in db.query(ik.CctrKbAptM.kb_qtn_rles_gd_cd).all()]

    m1 = {c.kb_complex_id: c
          for c in db.query(Complex).filter(Complex.kb_complex_id.in_(kbas)).all()}
    for m in db.query(ik.CctrKbAptM).all():
        f = complex_fields(m, stdng.get(m.kb_qtn_stdng_cd))
        c = m1.get(m.kb_qtn_rles_gd_cd)
        if c:
            for k, v in f.items():
                setattr(c, k, v)
        else:
            c = Complex(**f)  # is_active 는 모델 default=True
            db.add(c)
            db.flush()
            m1[m.kb_qtn_rles_gd_cd] = c
    db.commit()

    cids = [c.id for c in m1.values()]
    amap = {(a.complex_id, a.kb_area_code): a
            for a in db.query(Area).filter(Area.complex_id.in_(cids)).all()}
    for p in db.query(ik.CctrKbAptPntpI).all():
        c = m1.get(p.kb_qtn_rles_gd_cd)
        if not c:
            continue
        f = area_fields(p)
        a = amap.get((c.id, p.pntp_seqno))
        if a:
            for k, v in f.items():
                setattr(a, k, v)
        else:
            a = Area(complex_id=c.id, **f)
            db.add(a)
            db.flush()
            amap[(c.id, p.pntp_seqno)] = a
    db.commit()

    pmap = {(x.complex_id, x.area_id, x.as_of_date): x
            for x in db.query(KBPrice).filter(KBPrice.complex_id.in_(cids)).all()}
    for q in db.query(ik.CctrKbAptQtnL).all():
        c = m1.get(q.kb_qtn_rles_gd_cd)
        a = amap.get((c.id, q.pntp_seqno)) if c else None
        if not a:
            continue
        f = price_fields(q)
        key = (c.id, a.id, f["as_of_date"])
        x = pmap.get(key)
        if x:
            x.general_price, x.high_avg_price, x.low_avg_price = (
                f["general_price"], f["high_avg_price"], f["low_avg_price"])
        else:
            db.add(KBPrice(complex_id=c.id, area_id=a.id, source="oracle",
                           fetched_at=now, **f))
    db.commit()

    tkey = set()
    for x in db.query(Transaction.complex_id, Transaction.contract_date, Transaction.price,
                      Transaction.exclusive_m2, Transaction.floor
                      ).filter(Transaction.complex_id.in_(cids)).all():
        tkey.add(tuple(x))
    ins = 0
    for t in db.query(ik.CctrAptTxcsHist).all():
        c = m1.get(t.kb_qtn_rles_gd_cd)
        if not c:
            continue
        cd, pr = _date(t.tx_dt), _won(t.tx_amt)
        key = (c.id, cd, pr, t.apt_are, t.rlvn_flr)
        if key in tkey:
            continue
        tkey.add(key)
        db.add(Transaction(complex_id=c.id, contract_date=cd, price=pr,
                           exclusive_m2=t.apt_are, floor=t.rlvn_flr, source="oracle",
                           source_id=t.seqno, is_cancelled=False, fetched_at=now))
        ins += 1
    db.commit()
    print(f"apply 완료 — complexes/areas/kb_prices upsert, transactions 신규 {ins} insert.")


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--verify", action="store_true", help="기존 app-schema 와 대조만(기본)")
    g.add_argument("--apply", action="store_true", help="app-schema 로 멱등 upsert(dev 전용)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        if args.apply:
            if settings.data_mode != "dev":
                print(f"거부: data_mode={settings.data_mode} — --apply 는 dev 전용. 운영은 수집기 ETL.",
                      file=sys.stderr)
                sys.exit(2)
            _apply(db)
        else:
            _verify(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
