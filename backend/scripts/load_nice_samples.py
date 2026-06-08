"""NICE 등기부 6테이블 케이스 샘플(xlsx) → 앱 PG nice_rles_* 적재 (외부 테스트 픽스처).

사내 정보계 반입 전, 외부에서 registry_db_service(결정적 빌드+LTV)를 실제로 검증하기 위한
개발용 로더. 샘플은 `etc/테이블/등기부등본/샘플/`(로컬 전용, 미커밋)에서 읽는다.

ADR-011: 이 6테이블은 수집기 소유 read-only. 본 로더는 **개발 테스트 한정** 편의로
테이블을 drop+create 후 적재한다(운영/CI 실행 금지). 실 환경에선 수집기 ETL이 적재.

실행: 앱 PG(5433)에 닿는 DATABASE_URL 로
  DATABASE_URL=postgresql://kb_user:<pw>@localhost:5433/kb_estate \
    backend/.venv/bin/python backend/scripts/load_nice_samples.py
"""
import glob
import os
import sys
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import BigInteger, Integer  # noqa: E402

from core.config import settings  # noqa: E402
from core.database import SessionLocal, engine  # noqa: E402
from models import registry_nice as rn  # noqa: E402

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# 파일명 한글 키워드 → 모델. '표제부상세' 가 '상세' 와 충돌하므로 전체 토큰으로 구분.
KEYWORD_MODEL = [
    ("등기부등본기본", rn.NiceRlesBasic),
    ("등기부등본상세", rn.NiceRlesDetail),
    ("요약명세", rn.NiceRlesBrief),
    ("저당명세", rn.NiceRlesCollateral),
    ("당사자명세", rn.NiceRlesParty),
    ("표제부", rn.NiceRlesHeader),
]

SAMPLE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "etc", "테이블", "등기부등본", "샘플",
)


def _col_idx(ref: str) -> int:
    s = "".join(c for c in ref if c.isalpha())
    n = 0
    for c in s:
        n = n * 26 + (ord(c) - 64)
    return n - 1


def read_sheet(path: str) -> list[list[str]]:
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(f"{NS}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
        names = sorted(n for n in z.namelist()
                       if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
        root = ET.fromstring(z.read(names[0]))
        rows = []
        for r in root.iter(f"{NS}row"):
            cells = {}
            for c in r.findall(f"{NS}c"):
                ref = c.get("r", "")
                idx = _col_idx(ref) if ref else len(cells)
                t = c.get("t")
                v = c.find(f"{NS}v")
                isn = c.find(f"{NS}is")
                if t == "s" and v is not None and v.text is not None:
                    i = int(v.text)
                    val = shared[i] if i < len(shared) else ""
                elif t == "inlineStr" and isn is not None:
                    val = "".join(tt.text or "" for tt in isn.iter(f"{NS}t"))
                elif v is not None:
                    val = v.text or ""
                else:
                    val = ""
                cells[idx] = val
            if cells:
                rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
        return rows


def model_for(filename: str):
    for kw, model in KEYWORD_MODEL:
        if kw in filename:
            return model
    return None


def _convert(col, val: str):
    if val is None or str(val).strip() == "":
        return None
    if isinstance(col.type, (Integer, BigInteger)):
        try:
            return int(float(str(val).replace(",", "")))
        except ValueError:
            return None
    return str(val)


def main() -> None:
    if settings.data_mode != "dev":
        print(f"거부: data_mode={settings.data_mode} (dev 전용 로더). "
              "운영은 수집기 Oracle 미러가 nice_rles_* 를 소유한다.", file=sys.stderr)
        sys.exit(2)
    if not os.path.isdir(SAMPLE_DIR):
        print(f"샘플 디렉토리 없음: {SAMPLE_DIR}", file=sys.stderr)
        sys.exit(1)

    # per-table drop/create — metadata.drop_all 은 공유 ENUM(userrole 등)까지 건드리므로 피함.
    tables = [m.__table__ for _, m in KEYWORD_MODEL]
    for t in tables:
        t.drop(engine, checkfirst=True)
    for t in tables:
        t.create(engine, checkfirst=True)

    session = SessionLocal()
    counts: dict[str, int] = {}
    try:
        for path in sorted(glob.glob(os.path.join(SAMPLE_DIR, "*.xlsx"))):
            fname = os.path.basename(path)
            model = model_for(fname)
            if model is None:
                print(f"  스킵(매핑 없음): {fname}", file=sys.stderr)
                continue
            cols = {c.name: c for c in model.__table__.columns}
            rows = read_sheet(path)
            if not rows:
                continue
            header = [h.strip().lower() for h in rows[0]]
            n = 0
            for r in rows[1:]:
                if not any(str(c).strip() for c in r):
                    continue
                data = {}
                for i, val in enumerate(r):
                    name = header[i] if i < len(header) else None
                    if name and name in cols and name != "id":
                        data[name] = _convert(cols[name], val)
                session.add(model(**data))
                n += 1
            counts[model.__tablename__] = counts.get(model.__tablename__, 0) + n
        session.commit()
    finally:
        session.close()

    for tbl, n in sorted(counts.items()):
        print(f"  {tbl}: {n} rows")
    print("적재 완료.")


if __name__ == "__main__":
    main()
