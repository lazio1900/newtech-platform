"""DataSourceMapping 의 transform 함수 실제 구현.

entity_registry.TRANSFORM_REGISTRY 의 key 와 1:1 매칭. 적용 실패는 None.
운영 어댑터(Phase 2) 와 미리보기 API 가 공통으로 사용.
"""
from datetime import date, datetime
from typing import Any, Callable


def _to_int(v: Any) -> int | None:
    if v is None or v == '':
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).replace(',', '').strip()
    return int(float(s)) if s else None


def _to_float(v: Any) -> float | None:
    if v is None or v == '':
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return float(str(v).replace(',', '').strip())


def _to_str(v: Any) -> str | None:
    return None if v is None else str(v)


def _won_to_int(v: Any) -> int | None:
    if v is None or v == '':
        return None
    s = str(v).replace(',', '').replace('원', '').strip()
    return int(float(s)) if s else None


def _manwon_to_won(v: Any) -> int | None:
    n = _to_int(v)
    return None if n is None else n * 10000


def _date_yyyymmdd(v: Any) -> date | None:
    if v is None:
        return None
    s = str(v).strip().replace('-', '').replace('.', '').replace('/', '')
    if len(s) < 8:
        return None
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def _date_iso(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v).strip()[:10])


def _year_from_date(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, (date, datetime)):
        return f"{v.year}.{v.month:02d}"
    s = str(v)[:10]
    try:
        d = date.fromisoformat(s)
        return f"{d.year}.{d.month:02d}"
    except Exception:
        return s  # 이미 'YYYY.MM' 형식이면 그대로


def _bool_y_n(v: Any) -> bool | None:
    if v is None or v == '':
        return None
    return str(v).strip().upper() in ('Y', 'YES', 'TRUE', '1')


TRANSFORM_FUNCS: dict[str, Callable[[Any], Any]] = {
    'none':           lambda v: v,
    'to_int':         _to_int,
    'to_float':       _to_float,
    'to_str':         _to_str,
    'won_to_int':     _won_to_int,
    'manwon_to_won':  _manwon_to_won,
    'date_yyyymmdd':  _date_yyyymmdd,
    'date_iso':       _date_iso,
    'year_from_date': _year_from_date,
    'bool_y_n':       _bool_y_n,
}


def apply(transform_key: str | None, value: Any) -> Any:
    """transform 적용. 실패는 None."""
    fn = TRANSFORM_FUNCS.get(transform_key or 'none')
    if fn is None:
        return value
    try:
        return fn(value)
    except Exception:
        return None
