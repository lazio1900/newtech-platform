"""등기부등본 MinerU markdown → 전용면적(㎡) 추출.

MinerU 가 추출한 markdown 의 표제부(전유부분의 건물의 표시) 블록에서
"건물내역" 컬럼의 면적 수치를 뽑는다.

OCR 특성상 ㎡ 단위 표기가 m² / m2 / m&#x27;(apostrophe) / m 짤림 등
여러 형태로 나오므로 보수적으로 모두 허용.
"""
from __future__ import annotations

import re
from typing import Optional


_BLOCK_RE = re.compile(
    r"전유부분의\s*건물의\s*표시(.+?)(?:\(\s*대지권의\s*표시\s*\)|$)",
    re.DOTALL,
)
# 숫자(소수 1~2자리) + 단위 m. m² / m2 / m&#x27; / m(짤림) 모두 포함.
# 전유부분 블록 안으로 한정해 false positive 위험 낮춤.
_AREA_RE = re.compile(r"(\d{1,3}\.\d{1,2})\s*m")


def extract_exclusive_m2(markdown: str) -> Optional[float]:
    """등기부 markdown 에서 전용면적(㎡) 추출. 실패 시 None.

    전유부분 블록 안의 첫 번째 매칭을 사용 (표시번호 1 = 최초 등기 면적).
    변경 이력이 있어도 면적은 보통 동일.
    """
    if not markdown:
        return None
    m = _BLOCK_RE.search(markdown)
    if not m:
        return None
    block = m.group(1)
    am = _AREA_RE.search(block)
    if not am:
        return None
    try:
        return float(am.group(1))
    except ValueError:
        return None


if __name__ == "__main__":
    from pathlib import Path

    sample = Path("/tmp/mineru_sample.md")
    if sample.exists():
        md = sample.read_text()
        result = extract_exclusive_m2(md)
        assert result == 49.77, f"expected 49.77, got {result}"
        print(f"[ok] /tmp/mineru_sample.md → {result}㎡")

    # 변형 케이스 회귀 테스트
    cases = [
        ("(전유부분의 건물의 표시) ... 철근콘크리트조84.99m² ... (대지권의 표시)", 84.99),
        ("(전유부분의 건물의 표시) ... 철근콘크리트조 59.84 m2 ... (대지권의 표시)", 59.84),
        ("(전유부분의 건물의 표시) ... 철근콘크리트조114.55m&#x27; ... (대지권의 표시)", 114.55),
        ("(전유부분의 건물의 표시) ... 철근콘크리트조49.77m ... (대지권의 표시)", 49.77),
        ("(전유부분의 건물의 표시) ... 정보없음 ... (대지권의 표시)", None),
        ("표제부 만 있고 전유부분 블록 없음", None),
    ]
    for md, expected in cases:
        got = extract_exclusive_m2(md)
        assert got == expected, f"case fail: md={md!r} expected={expected} got={got}"
        print(f"[ok] {expected} ← {md[:40]}...")
    print("all cases passed")
