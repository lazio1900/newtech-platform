"""골든 등기부 8건 파싱 + KB 단지 매칭 → /tmp/mock_golden_records.json.

build_monitoring_mock 빌더(W3)가 소비할 중간 산출물 생성.
설계 단일 출처: docs/internal-migration-monitoring-mock-spec.md §1·§2·§5.

실행:
  /Users/lmj/00_projects/newtech-platform/backend/.venv/bin/python \
      /Users/lmj/00_projects/newtech-platform/backend/scripts/_mock_golden.py
DB URL 은 /tmp/mock_db_url.txt(한 줄)에서 읽는다.
"""
import json
import re
from pathlib import Path

from sqlalchemy import create_engine, text

GOLDEN_DIR = Path(
    "/Users/lmj/00_projects/openwebui_chatbot/ocr_task/기업금융팀/golden/extracted"
)
DB_URL_FILE = Path("/tmp/mock_db_url.txt")
OUT_FILE = Path("/tmp/mock_golden_records.json")

SLUGS = ["garak", "mokdong", "areum", "sinnae", "misa", "sinchon", "junggye", "imin"]


def normalize_apt(name: str) -> str:
    if not name:
        return ""
    name = name.replace("이편한세상", "e편한세상")
    name = re.sub(r"\([^)]*\)", "", name)  # 괄호 토큰(빌더) 제거
    name = re.sub(r"아파트$", "", name)
    name = name.replace(" ", "")
    return name


# 부동산표시: "시도 구 동 지번 단지명 제N동 제N층 제N호"
_ADDR_RE = re.compile(
    r"^(?P<si>\S+?(?:특별시|광역시|특별자치시|특별자치도|도))\s*"
    r"(?P<rest>.+)$"
)
_DONG_RE = re.compile(r"(?P<gu>\S+?(?:구|시|군))?\s*(?P<dong>\S+?(?:동|읍|면|리|가))(?=\d|\s)")
_HO_RE = re.compile(r"제?\s*(?P<dong_no>\d+)\s*동\s*(?:제?\s*\d+\s*층)?\s*제?\s*(?P<ho>\d+)\s*호")


def parse_addr(raw: str) -> dict:
    raw = (raw or "").strip()
    si = gu = dong = ""
    m = _ADDR_RE.match(raw)
    body = raw
    if m:
        si = m.group("si")
        body = m.group("rest")
    dm = _DONG_RE.search(body)
    if dm:
        gu = (dm.group("gu") or "").strip()
        dong = dm.group("dong").strip()
    return {"si": si, "gu": gu, "dong": dong, "raw": raw}


def parse_apt_nm(raw: str, dong: str) -> str:
    """부동산표시에서 단지명 추출: 지번(숫자) 다음, 제N동 이전 토큰."""
    body = raw
    # 동 이름 이후로 자르기
    if dong and dong in body:
        body = body.split(dong, 1)[1]
    # 선두 지번/필지 표기 제거 (예: "650", "143", "1013외 3필지", "369 ", "102 ")
    body = re.sub(r"^\s*\d+(?:-\d+)?(?:외\s*\d+\s*필지)?\s*", "", body)
    # 제N동... 이후 절단
    body = re.split(r"제?\s*\d+\s*동", body)[0]
    return body.strip()


_DIGIT_AMT = re.compile(r"[\d,]+")


def parse_amount(raw: str):
    """채권최고액 문자열 → 정수(원). 아라비아 숫자가 없으면(순한글금액) None."""
    if not raw:
        return None
    s = raw.replace("금", "").replace("원", "").replace("정", "").strip()
    m = _DIGIT_AMT.search(s)
    if not m:
        return None
    digits = m.group(0).replace(",", "")
    if not digits:
        return None
    return int(digits)


def live_liens(eulgu: list) -> list:
    out = []
    for e in eulgu:
        if "근저당권설정" not in (e.get("등기목적") or ""):
            continue
        if e.get("말소"):
            continue
        amt = parse_amount(e.get("채권최고액"))
        if amt is None:
            continue  # 순한글금액/공란은 합산 제외 (아라비아 중복행이 따로 존재)
        out.append({"권리자": (e.get("권리자") or "").strip(), "amt": amt})
    return out


def pick_area_and_price(conn, complex_id: int, exclusive_m2):
    """전용면적 있으면 최근접, 없으면 대표(중앙값) area. 최근 kb_price 동반."""
    areas = conn.execute(
        text(
            "select id, exclusive_m2, kb_area_code from areas "
            "where complex_id=:cid and exclusive_m2 is not null order by exclusive_m2"
        ),
        {"cid": complex_id},
    ).fetchall()
    if not areas:
        return None, None, None, None
    if exclusive_m2:
        area = min(areas, key=lambda a: abs((a.exclusive_m2 or 0) - exclusive_m2))
    else:
        area = areas[len(areas) // 2]  # 중앙값 평형
    price = conn.execute(
        text(
            "select as_of_date, general_price, high_avg_price, low_avg_price "
            "from kb_prices where area_id=:aid order by as_of_date desc limit 1"
        ),
        {"aid": area.id},
    ).fetchone()
    if price is None:
        price = conn.execute(
            text(
                "select as_of_date, general_price, high_avg_price, low_avg_price "
                "from kb_prices where complex_id=:cid order by as_of_date desc limit 1"
            ),
            {"cid": complex_id},
        ).fetchone()
    recent_price = base_date = None
    if price is not None:
        recent_price = price.general_price
        if recent_price is None:
            hi, lo = price.high_avg_price, price.low_avg_price
            if hi is not None and lo is not None:
                recent_price = (hi + lo) // 2
            else:
                recent_price = hi if hi is not None else lo
        base_date = price.as_of_date.isoformat() if price.as_of_date else None
    return area.kb_area_code, recent_price, base_date, area.exclusive_m2


def match_complex(conn, apt_nm: str, addr: dict):
    """정규화 + 행정구역 핀으로 단일 complex 매칭. 모호/미발견이면 (None, note)."""
    norm = normalize_apt(apt_nm)
    dong = addr.get("dong") or ""
    if not norm:
        return None, "단지명 파싱 실패"
    # DB 이름도 동일 정규화(괄호/공백 제거 + 이편한세상→e편한세상)해 LIKE 대칭 보장
    db_norm = (
        "replace(regexp_replace(replace(name,'이편한세상','e편한세상'),"
        "'\\([^)]*\\)','','g'),' ','')"
    )
    rows = conn.execute(
        text(
            f"select id, kb_complex_id, name, dong_name, dong_code, region_code, "
            f"built_year, total_households from complexes "
            f"where {db_norm} ilike :pat"
        ),
        {"pat": f"%{norm}%"},
    ).fetchall()
    if dong:
        pinned = [r for r in rows if (r.dong_name or "") == dong]
        if pinned:
            rows = pinned
    if not rows:
        return None, f"정규화('{norm}')+동핀('{dong}') 후 미발견 (KB 누락 가능)"
    # 정확 일치(정규화 동일) 우선
    exact = [r for r in rows if normalize_apt(r.name) == norm]
    cand = exact or rows
    if len(cand) > 1:
        names = ", ".join(f"{r.name}({r.kb_complex_id})" for r in cand[:6])
        return None, f"동명 모호 {len(cand)}건 [{names}] — 억지매칭 금지"
    return cand[0], "정확 매칭" if exact else f"정규화 매칭('{norm}')"


def main():
    eng = create_engine(DB_URL_FILE.read_text().strip())
    records = []
    matched_slugs, unmatched_slugs = [], []
    with eng.connect() as conn:
        for slug in SLUGS:
            data = json.loads((GOLDEN_DIR / f"{slug}.json").read_text(encoding="utf-8"))
            rles = (data.get("고유번호") or "").replace("-", "")
            raw_disp = data.get("부동산표시") or ""
            addr = parse_addr(raw_disp)
            apt_nm = parse_apt_nm(raw_disp, addr["dong"])
            ho_m = _HO_RE.search(raw_disp)
            dong_ho = (
                f"{ho_m.group('dong_no')}동 {ho_m.group('ho')}호" if ho_m else ""
            )
            owners = data.get("현소유자") or []
            owner_nm = ", ".join(o.get("이름", "").strip() for o in owners if o.get("이름"))
            liens = live_liens(data.get("을구") or [])
            prior_total = sum(l["amt"] for l in liens)

            cx, note = match_complex(conn, apt_nm, addr)
            rec = {
                "slug": slug,
                "rles_unq_no": rles,
                "apt_nm": apt_nm,
                "addr": addr,
                "dong_ho": dong_ho,
                "owner_nm": owner_nm,
                "prior_liens": liens,
                "prior_total": prior_total,
                "exclusive_m2": None,
                "matched": False,
                "kb_complex_id": None,
                "kb_area_code": None,
                "kb_stdng_cd": None,
                "kb_recent_price": None,
                "kb_base_date": None,
                "built_year": None,
                "total_households": None,
                "match_note": note,
            }
            if cx is not None:
                area_code, price, base_date, ex_m2 = pick_area_and_price(conn, cx.id, None)
                rec.update(
                    matched=True,
                    kb_complex_id=cx.kb_complex_id,
                    kb_area_code=area_code,
                    kb_stdng_cd=cx.dong_code,
                    kb_recent_price=price,
                    kb_base_date=base_date,
                    exclusive_m2=ex_m2,
                    built_year=cx.built_year,
                    total_households=cx.total_households,
                )
                matched_slugs.append(slug)
            else:
                unmatched_slugs.append(slug)
            records.append(rec)

    OUT_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"matched {len(matched_slugs)}/{len(SLUGS)}")
    print(f"  matched: {matched_slugs}")
    print(f"  unmatched: {unmatched_slugs}")
    for r in records:
        price = r["kb_recent_price"]
        price_s = f"{price:,}" if price is not None else "—"
        print(
            f"  {r['slug']:8s} prior_total={r['prior_total']:>14,} "
            f"kb_recent_price={price_s:>16} matched={r['matched']} "
            f"({r['match_note']})"
        )


if __name__ == "__main__":
    main()
