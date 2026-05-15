"""LLM 기반 등기부등본 권리 분석.

흐름:
  ic_id → 등기부 API 8100 에서 PDF 받기 → MinerU API 8200 으로 markdown 변환
       → LLM (JSON mode) 1차 → 결정적 게이트 + LLM critique → 필요 시 재생성
       → loan_applications.ai_rights_text 에 캐시
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from core.config import settings
from models.loan import LoanApplication

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """당신은 한국 등기부등본 분석 전문가입니다.
주어진 등기부등본 텍스트를 분석해 JSON 으로 반환합니다.

JSON 키:
- "ownership_entries": 갑구 소유지분현황 array. 각 항목은
    {"name": "이OO", "reg_number": "*-*-*", "share": "1/1", "address": "서울특별시...", "rank_number": 1}
- "ownership_other_entries": 갑구 소유권 외 사항 array (가압류/가처분/경매개시 등). 각 항목은
    {"rank_number": 1, "purpose": "가압류", "receipt_info": "2024년...", "details": "..."}
- "mortgage_entries": 을구 (근)저당권/전세권/근질권 array. 각 항목은
    {"rank_number": "1-1", "purpose": "근저당권설정", "receipt_info": "2024년1월15일\n제12345호", "main_details": "채권최고액 금500,000,000원\n채무자 이OO\n근저당권자 KB국민은행", "target_owner": "이OO"}
    - target_owner 는 해당 근저당이 설정된 소유자 이름. 등기부의 "대상소유자" 또는 채무자(소유자와 동일한 경우) 에서 추출.
    - purpose 는 등기부 원문 표기 그대로: "근저당권설정" / "근저당권변경" / "근저당권이전" / "근질권설정" / "전세권설정" 등. 임의로 통일하지 말 것.
- "max_bond_amount": 선순위 채권최고액 합계 (원, 정수).
    **계산 규칙 — 매우 중요. "채권최고액"이 적힌 모든 항목을 무조건 더하지 말 것.**
    1) 합산 대상: purpose 가 "근저당권설정" 인 활성 항목의 채권최고액만.
    2) 합산 제외:
       - "근질권설정" (제3채권자가 근저당권자의 채권에 대해 갖는 권리 — 동일 근저당 위에 얹힌 권리이므로 이미 (1) 에 포함된 부담을 이중계상하면 안 됨)
       - "근저당권이전" (같은 근저당의 채권자 변경 — 부담 총액 불변)
       - "근저당권변경" (같은 순위 근저당의 채무자·채권최고액 등 변경)
    3) "근저당권변경" 으로 채권최고액이 갱신된 경우: 동일 순위(rank_number 의 주 번호; "1-2" → "1") 에 속한 가장 최신 변경의 채권최고액으로 그 근저당의 금액을 **덮어쓴 뒤** 합산. 원래 설정액과 변경액을 둘 다 더하지 말 것.
    4) 요약 페이지가 "을구 - 기록사항 없음" 이면 0.
- "tenant_deposit": 선순위 임차보증금 (원, 정수). 등기부에 있으면, 없으면 0
- "gap_summary":  갑구 소유권/이전이력 자연어 요약 2~3문장
- "eul_summary":  을구 (근)저당/전세권 자연어 요약 2~3문장
- "seizure_summary": 가압류·가처분·경매 등 권리 침해 자연어 요약 2~3문장 (없으면 "없음" 명시)
- "priority_summary": 선순위/대항력 분석 자연어 2~3문장
- "comprehensive_opinion": 종합 의견 2~3문장 (담보 적격성 관점)

작성 규칙:
- 모든 *_summary 와 comprehensive_opinion 은 한국어 존대형(~합니다) 평문
- 마크다운/번호 금지
- 텍스트에 없는 정보는 추측 금지. 없으면 "기록사항 없음" 또는 빈 array
- max_bond_amount / tenant_deposit 는 원 단위 정수 (원문이 "5억" 이면 500000000)
- main_details / details 내부에 표기되는 금액은 천 단위 콤마 + "원" (예: "금500,000,000원"). 자릿수 누락 금지.
- 항목별 줄바꿈은 "\\n" 으로 (rendering 시 줄바꿈으로 보이도록)

**말소사항 처리 — 가장 중요**:
등기부 끝부분에 "주요 등기사항 요약 (참고용)" 섹션이 있으면, 이 요약 페이지가 현재 유효한(말소되지 않은)
권리의 단일 출처(SSOT) 입니다. 본문 표에는 말소된 과거 권리도 함께 인쇄되어 있고 말소선이 markdown 으로
보존되지 않아, 본문만 보면 말소 항목을 활성으로 오인합니다.

규칙:
1. ownership_entries ← **반드시 요약 "1. 소유지분현황 ( 갑구 )" 표의 행만 그대로** 포함. 다른 어떤 곳에서도 가져오지 말 것.
   - 요약 표의 행 수 = ownership_entries 길이. 요약에 1명이면 ownership_entries 도 정확히 1개.
   - 본문 갑구의 "소유권보존(rank 1)", "소유권이전(rank 2,3,4...)" 같은 과거 매매이력의 사람들은 **현재 소유자가 아님 → 절대 포함 금지**.
   - 요약에서 "단독소유" 인데 ownership_entries 가 2명 이상이면 명백한 오류.
2. ownership_other_entries ← 요약 "2. 소유지분을 제외한..." 가 "- 기록사항 없음" 이면 빈 array. 표가 있으면 그 표의 **모든 행** 을 포함.
3. mortgage_entries ← 요약 "3. (근)저당권 및 전세권 등 ( 을구 )" 가 "- 기록사항 없음" 이면 빈 array.
   **표가 있으면 그 표의 모든 행을 활성 mortgage_entries 로 빠짐없이 포함하세요.** 요약에 있는 항목은 모두 현재 유효한 권리이며 절대 말소가 아닙니다.
4. 본문 표(을구/갑구) 에만 있고 요약에 없는 항목 → 말소된 것으로 간주해서 제외.
5. max_bond_amount: 요약 mortgage_entries 의 채권최고액 합계 (원, 정수). 요약이 "기록사항 없음" 이면 0.
6. **rank_number 는 반드시 요약 페이지의 "순위번호" 열 값을 그대로 사용.** 본문 표의 순위번호와 다르더라도 요약 우선.
   (요약은 등기부 전체에서의 실제 순위번호를 반영하고, 본문은 페이지/표 내 일련번호일 수 있음)
7. 본문 표는 receipt_info / main_details / 채무자·근저당권자 이름 등 상세 보강 용으로만 사용. 활성/말소 판단과 rank_number 의 근거로 쓰지 말 것.
8. 요약 페이지가 없는 등기부면 본문에서 "근저당권설정등기말소" 같은 명시적 말소 표식을 단서로 활성/말소 판단.
"""


def _fetch_pdf_blob(ic_id: int) -> Optional[bytes]:
    """등기부 API 8100 에서 PDF binary 를 받아온다."""
    if not settings.registry_internal_token:
        logger.warning("REGISTRY_INTERNAL_TOKEN 미설정")
        return None
    try:
        with httpx.Client(timeout=30) as client:
            r = client.get(
                f"{settings.registry_api_url}/v1/registry/{ic_id}/pdf",
                headers={"X-Internal-Token": settings.registry_internal_token},
            )
        if r.status_code != 200:
            logger.warning(f"[ai_rights] PDF fetch {ic_id}: HTTP {r.status_code}")
            return None
        return r.content
    except Exception as e:
        logger.warning(f"[ai_rights] PDF fetch {ic_id} failed: {e}")
        return None


def _fetch_cached_markdown(ic_id: int) -> Optional[str]:
    """등기부 API 가 PDF 발급 시 함께 저장한 MinerU markdown 을 받아온다.

    캐시 hit 이면 MinerU 재호출 회피 (속도·비용 절감). 미생성/404 이면 None.
    """
    if not settings.registry_internal_token:
        return None
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(
                f"{settings.registry_api_url}/v1/registry/{ic_id}/markdown",
                headers={"X-Internal-Token": settings.registry_internal_token},
            )
        if r.status_code != 200:
            return None
        md = (r.json() or {}).get("markdown")
        return md if isinstance(md, str) and md.strip() else None
    except Exception:
        return None


def _extract_md_from_mineru_response(data) -> str:
    """MinerU /file_parse JSON 응답에서 markdown 텍스트 추출.

    응답 스키마가 버전에 따라 다를 수 있어 흔한 경로 몇 군데를 본다.
      - {"results": {"<fname>": {"md_content": "..."}}}
      - {"results": [{"md_content": "..."}]}
      - {"md_content"|"markdown"|"md": "..."}
    """
    if not isinstance(data, dict):
        return ""
    results = data.get("results")
    if isinstance(results, dict):
        for v in results.values():
            if isinstance(v, dict):
                for k in ("md_content", "markdown", "md"):
                    if isinstance(v.get(k), str) and v[k].strip():
                        return v[k]
    if isinstance(results, list):
        for v in results:
            if isinstance(v, dict):
                for k in ("md_content", "markdown", "md"):
                    if isinstance(v.get(k), str) and v[k].strip():
                        return v[k]
    for k in ("md_content", "markdown", "md"):
        if isinstance(data.get(k), str) and data[k].strip():
            return data[k]
    return ""


def _extract_markdown(pdf_bytes: bytes) -> str:
    """등기부등본 PDF → MinerU API 호출로 markdown 변환.

    실패 시 빈 문자열 반환 (호출부가 처리). silent fallback 없음 — 로그로 명시.
    """
    url = f"{settings.mineru_api_url}/file_parse"
    try:
        with httpx.Client(timeout=settings.mineru_request_timeout) as client:
            r = client.post(
                url,
                files={"files": ("registry.pdf", pdf_bytes, "application/pdf")},
                data={
                    "return_md": "true",
                    "backend": "pipeline",
                    "lang_list": "korean",
                },
            )
    except Exception as e:
        logger.warning(f"[ai_rights] MinerU request failed: {e}")
        return ""

    if r.status_code != 200:
        logger.warning(f"[ai_rights] MinerU HTTP {r.status_code}: {r.text[:300]}")
        return ""

    try:
        data = r.json()
    except ValueError:
        logger.warning(f"[ai_rights] MinerU non-JSON response: {r.text[:300]}")
        return ""

    md = _extract_md_from_mineru_response(data)
    if not md:
        keys = list(data.keys()) if isinstance(data, dict) else type(data).__name__
        logger.warning(f"[ai_rights] MinerU response had no markdown (top-level={keys})")
        return md
    # MinerU 가 추출한 이미지 참조는 분석에 무의미 → 토큰 절약차 제거
    md = re.sub(r"!\[\]\(images/[^)]+\)", "", md)
    return md.strip()


def _flatten(val) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, list):
        return " ".join(_flatten(v) for v in val)
    if isinstance(val, dict):
        return " ".join(f"{k}: {_flatten(v)}" for k, v in val.items())
    return str(val).strip()


def _empty_result() -> dict:
    return {
        "ownership_entries": [],
        "ownership_other_entries": [],
        "mortgage_entries": [],
        "max_bond_amount": 0,
        "tenant_deposit": 0,
        "gap_summary": "",
        "eul_summary": "",
        "seizure_summary": "",
        "priority_summary": "",
        "comprehensive_opinion": "",
    }


# 채권최고액 패턴. "채권최고액 금 1,500,000,000원" / "채권최고액금500,000,000원" 등 변형 허용.
_MORTGAGE_AMOUNT_RE = re.compile(r"채권최고액\s*금?\s*([\d,]+)\s*원")
# 합산에서 제외해야 할 등기 유형. 매치 직전 200자 윈도우에 등장하면 그 채권최고액은 근저당설정 항목이 아님.
_NON_SETTING_PURPOSE_RE = re.compile(r"근질권|근저당권변경|근저당권이전|전세권")


def _extract_mortgage_amounts(text: str) -> list[int]:
    """원문 markdown 에서 활성 근저당권설정의 '채권최고액 금 XXX원' 만 추출.

    근질권·근저당권변경·근저당권이전·전세권에 딸린 채권최고액은 제외 (max_bond_amount
    합계에 합산되지 않아야 하는 항목 — 이중계상 방지).
    """
    amounts: list[int] = []
    for m in _MORTGAGE_AMOUNT_RE.finditer(text):
        window = text[max(0, m.start() - 200): m.start()]
        if _NON_SETTING_PURPOSE_RE.search(window):
            continue
        try:
            amounts.append(int(m.group(1).replace(",", "")))
        except ValueError:
            continue
    return amounts


_SUMMARY_EUL_EMPTY_RE = re.compile(
    r"3\.\s*\(?근?\)?저당권\s*및\s*전세권\s*등\s*\(\s*을구\s*\)\s*[\r\n\s\\-]*기록사항\s*없음",
    re.MULTILINE,
)
_SUMMARY_GAP_OTHER_EMPTY_RE = re.compile(
    r"2\.\s*소유지분을?\s*제외한\s*소유권에\s*관한\s*사항\s*\(\s*갑구\s*\)\s*[\r\n\s\\-]*기록사항\s*없음",
    re.MULTILINE,
)
# 요약 페이지 "1. 소유지분현황 (갑구)" 내 "단독소유" 표시. 있으면 ownership_entries 정확히 1명.
_SUMMARY_SOLE_OWNER_RE = re.compile(r"단\s*독\s*소\s*유")


def _summary_says_no_mortgages(text: str) -> bool:
    """등기부 요약 페이지의 "3. (근)저당권... ( 을구 ) - 기록사항 없음" 패턴."""
    return bool(_SUMMARY_EUL_EMPTY_RE.search(text))


def _summary_says_no_gap_other(text: str) -> bool:
    """요약 페이지의 "2. 소유지분을 제외한... ( 갑구 ) - 기록사항 없음" 패턴."""
    return bool(_SUMMARY_GAP_OTHER_EMPTY_RE.search(text))


def _deterministic_issues(text: str, parsed: dict) -> list[str]:
    """결정적 게이트. 환각·누락이 명확한 경우만 보수적으로 flag.

    1. 요약 페이지의 "을구 기록사항 없음" 인데 LLM 이 mortgage_entries 를 채운 경우 → 말소 미구분 의심
    2. 요약 페이지의 "갑구 소유권외 기록사항 없음" 인데 ownership_other_entries 채운 경우
    3. 원문 단일 채권최고액 > LLM max_bond_amount → 누락 의심
    """
    issues: list[str] = []

    if _summary_says_no_mortgages(text):
        mortgages = parsed.get("mortgage_entries") or []
        claimed_bond = int(parsed.get("max_bond_amount") or 0)
        if mortgages or claimed_bond > 0:
            issues.append(
                f"등기부 요약 페이지가 '을구 - 기록사항 없음' 으로 명시하는데 "
                f"mortgage_entries={len(mortgages)}건, max_bond_amount={claimed_bond:,}원 으로 채워져 있습니다. "
                f"본문 표의 말소된 과거 근저당권을 활성으로 잘못 분류했을 가능성이 큽니다. "
                f"요약 페이지 기준으로 mortgage_entries=[] 및 max_bond_amount=0 으로 정정하세요."
            )

    if _summary_says_no_gap_other(text):
        gap_other = parsed.get("ownership_other_entries") or []
        if gap_other:
            issues.append(
                f"등기부 요약 페이지가 '갑구 소유권외 - 기록사항 없음' 으로 명시하는데 "
                f"ownership_other_entries={len(gap_other)}건이 들어있습니다. "
                f"말소된 가압류·가처분 등을 활성으로 잘못 분류했을 가능성. 요약 기준으로 빈 array 로 정정하세요."
            )

    # 요약 페이지에 "단독소유" 표기가 있으면 ownership_entries 가 1명이어야 정상.
    # 본문 갑구의 이전 소유자가 끼어 들어간 케이스 자동 감지.
    if _SUMMARY_SOLE_OWNER_RE.search(text):
        owners = parsed.get("ownership_entries") or []
        if len(owners) > 1:
            names = [o.get("name") for o in owners if isinstance(o, dict)]
            issues.append(
                f"요약 페이지 '소유지분현황' 이 '단독소유' 1명인데 ownership_entries 에 "
                f"{len(owners)}명({names})이 있습니다. 본문 갑구의 이전 소유자(rank 1·2·3 매매이력) 가 "
                f"잘못 포함된 것 — 현재 소유자(요약 페이지 표의 그 한 명) 만 남기세요."
            )

    # 누락 의심: 원문 단일 최고액 > claimed (요약이 비어있다고 위에서 잡힌 케이스는 제외)
    if not _summary_says_no_mortgages(text):
        amounts = _extract_mortgage_amounts(text)
        if amounts:
            try:
                claimed = int(parsed.get("max_bond_amount") or 0)
            except (ValueError, TypeError):
                claimed = 0
            max_in_text = max(amounts)
            if max_in_text > claimed:
                issues.append(
                    f"원문에서 채권최고액 {max_in_text:,}원 항목이 발견됐으나 "
                    f"max_bond_amount 가 {claimed:,}원 으로 더 작습니다. "
                    f"근저당권 누락 또는 합산 누락 여부를 확인하세요."
                )

    return issues


CRITIQUE_PROMPT = """당신은 한국 등기부등본 분석 결과를 검증하는 전문가입니다.
원문(markdown) 과 1차 분석 결과(JSON) 를 비교해 누락·오류·환각을 검사합니다.

**우선 원칙 — 말소사항 구분**:
원문 끝에 "## 주요 등기사항 요약 (참고용)" / "주요 등기사항 요약" 섹션이 있으면,
**이것이 현재 유효한 권리의 단일 출처(SSOT)** 입니다. 본문 표에는 말소된 과거 권리도 인쇄되어 있고
말소선이 markdown 에 보존되지 않으므로, 1차 결과가 본문 표만 보고 말소 항목을 활성으로 잘못 분류했을 가능성이 큽니다.

검사 항목:
1. ownership_entries: 요약의 "1. 소유지분현황 ( 갑구 )" 표와 **행 수가 일치하는지** (이름·지분·등기번호·주소·순위번호).
   - 요약 표가 1행(예: 홍성석 단독소유)인데 1차 결과에 2명 이상이면 **반드시 issue** — 본문 갑구의 이전 소유자가 잘못 들어간 것. 정정 필요.
   - "단독소유" 인 사람과 다른 지분 표기의 사람이 함께 있으면 같은 사항.
2. ownership_other_entries: 요약의 "2. 소유지분을 제외한..." 와 일치. 요약이 "기록사항 없음" 이면 1차 결과도 빈 array 여야 함.
3. mortgage_entries: 요약의 "3. (근)저당권 및 전세권 등 ( 을구 )" 와 일치.
   - **요약이 "기록사항 없음" 인데 1차 결과에 mortgage_entries 가 들어있으면 모두 말소된 항목을 활성으로 잘못 분류한 것 — 반드시 issue 로 기록.**
   - 요약에 N건 있는데 1차 결과가 더 많으면 추가분은 말소 의심.
   - **rank_number 는 요약 페이지의 "순위번호" 와 일치해야 함.** 본문 표의 페이지내 순번과 다르면 issue.
4. mortgage_entries[*].target_owner: 갑구 소유자 또는 원문의 "대상소유자" 열과 일치. OCR 잡음(예: '박혜민' → '유옥') 으로 변형된 이름은 issue.
5. max_bond_amount: 활성(요약 기준) **근저당권설정** 항목의 채권최고액만 합산했는지 검증.
   - "근질권설정" / "근저당권이전" / "근저당권변경" 항목의 채권최고액을 별도 가산하지 않았는지 확인 (이중계상 issue).
   - "근저당권변경" 으로 채권최고액이 갱신된 근저당은 변경 후 최신 금액만 반영되어야 함. 원금+변경금 둘 다 더해져 있으면 issue.
   - 요약이 "기록사항 없음" 이면 0.
6. tenant_deposit: 임차보증금 누락 여부.
7. *_summary 필드: 원문에 없는 정보를 추측하지 않았는지.

응답은 JSON 으로만:
{"issues": ["어떤 필드의 무엇이 어떻게 잘못됐는지 1문장", "..."]}

문제가 없으면 {"issues": []}.
- 사소한 표현 차이는 issue 아님. 사실관계가 다를 때만 작성.
- 말소된 항목을 LLM 이 제외한 것은 옳은 동작이므로 issue 아님.
"""


def _run_critique(client, db, text: str, pass1_json: str) -> list[str]:
    """LLM self-critique. 발견된 issues list. 실패 시 빈 list."""
    from services.prompt_registry import get_prompt
    user = (
        f"원문 (markdown):\n\n{text}\n\n"
        f"1차 분석 결과(JSON):\n\n{pass1_json}\n\n"
        "위 두 입력을 비교해 issues 를 JSON 으로 답하세요."
    )
    try:
        critique_prompt = get_prompt(db, "rights", "critique", CRITIQUE_PROMPT)
        result = client.complete(user, system=critique_prompt, json_mode=True)
        raw = (result.get("text") or "").strip()
        if not raw:
            return []
        parsed = json.loads(raw)
        return [str(x).strip() for x in (parsed.get("issues") or []) if str(x).strip()]
    except Exception as e:
        logger.warning(f"[ai_rights] critique failed: {e}")
        return []


def generate_or_get_cached(
    db: Session,
    application_id: Optional[str],
    registry_ic_id: Optional[int],
) -> dict:
    """등기부 LLM 분석 결과 dict 반환.

    캐시 우선, 없으면 PDF 추출 + LLM 호출. 실패 시 빈 dict.
    """
    if not registry_ic_id:
        return _empty_result()

    app = None
    if application_id:
        app = db.query(LoanApplication).filter(LoanApplication.id == application_id).first()
        if app and app.ai_rights_text:
            try:
                return json.loads(app.ai_rights_text)
            except json.JSONDecodeError:
                pass  # 캐시 깨짐 → 재생성

    # 등기부 API 가 PDF 발급 시 캐싱한 markdown 우선 사용 (MinerU 재호출 회피).
    text = _fetch_cached_markdown(registry_ic_id) or ""
    if not text:
        pdf_bytes = _fetch_pdf_blob(registry_ic_id)
        if not pdf_bytes:
            return _empty_result()
        text = _extract_markdown(pdf_bytes)
    if not text.strip():
        logger.warning(f"[ai_rights] {registry_ic_id}: empty PDF text")
        return _empty_result()

    # gpt-4o 128k context. 복잡 등기부에서 후순위/말소사항 누락 방지차 cap 완화.
    MAX_CHARS = 80000
    if len(text) > MAX_CHARS:
        logger.warning(f"[ai_rights] {registry_ic_id}: text {len(text)} > {MAX_CHARS}, truncating")
        text = text[:MAX_CHARS]

    user_prompt = (
        f"등기부등본 (MinerU markdown, ic_id={registry_ic_id}):\n"
        "- 섹션은 '##' 헤더 (표제부 / 갑구 / 을구).\n"
        "- 표는 HTML <table> 또는 마크다운 파이프 표로 보존됨. rowspan/colspan 있을 수 있음.\n"
        "- 일부 글자가 OCR 노이즈로 깨졌을 수 있음. 동일 정보가 다른 행에 정상 표기된 경우 그쪽을 신뢰.\n\n"
        f"{text}\n\n"
        "위 등기부 내용을 시스템 메시지의 JSON 스키마에 맞게 응답하세요."
    )

    try:
        from services.llm_service import LLMClient
        from services.prompt_registry import get_prompt
        client = LLMClient()
        system_prompt = get_prompt(db, "rights", "system", SYSTEM_PROMPT)
        result = client.complete(user_prompt, system=system_prompt, json_mode=True)
        raw = (result.get("text") or "").strip()
        if not raw:
            return _empty_result()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"[ai_rights] JSON parse failed: {e}")
            return _empty_result()

        # 자기검증 단계: 결정적 게이트 + LLM critique 로 issue 수집, 있으면 1회 재생성.
        pass1_json = json.dumps(parsed, ensure_ascii=False)
        issues = _deterministic_issues(text, parsed)
        issues += _run_critique(client, db, text, pass1_json)
        if issues:
            logger.info(
                f"[ai_rights] {registry_ic_id}: critique issues={len(issues)}, regenerating"
            )
            regen_prompt = (
                f"등기부등본 (markdown 정제, ic_id={registry_ic_id}):\n\n{text}\n\n"
                f"1차 분석 결과(JSON):\n\n{pass1_json}\n\n"
                f"검증 단계에서 다음 문제가 지적됐습니다:\n"
                + "\n".join(f"- {i}" for i in issues)
                + "\n\n지적사항을 반영해 시스템 메시지의 JSON 스키마로 전체 결과를 재생성하세요."
            )
            try:
                result2 = client.complete(regen_prompt, system=system_prompt, json_mode=True)
                raw2 = (result2.get("text") or "").strip()
                parsed2 = json.loads(raw2) if raw2 else None
                if parsed2:
                    parsed = parsed2
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"[ai_rights] regen failed: {e}, falling back to pass1")

        # 응답 정규화 — list 보장, summary 평문화
        out = _empty_result()
        out["ownership_entries"] = parsed.get("ownership_entries") or []
        out["ownership_other_entries"] = parsed.get("ownership_other_entries") or []
        out["mortgage_entries"] = parsed.get("mortgage_entries") or []
        try:
            out["max_bond_amount"] = int(parsed.get("max_bond_amount") or 0)
        except (ValueError, TypeError):
            out["max_bond_amount"] = 0
        try:
            out["tenant_deposit"] = int(parsed.get("tenant_deposit") or 0)
        except (ValueError, TypeError):
            out["tenant_deposit"] = 0
        out["gap_summary"] = _flatten(parsed.get("gap_summary"))
        out["eul_summary"] = _flatten(parsed.get("eul_summary"))
        out["seizure_summary"] = _flatten(parsed.get("seizure_summary"))
        out["priority_summary"] = _flatten(parsed.get("priority_summary"))
        out["comprehensive_opinion"] = _flatten(parsed.get("comprehensive_opinion"))

        if app:
            app.ai_rights_text = json.dumps(out, ensure_ascii=False)
            app.ai_rights_generated_at = datetime.utcnow()
            db.commit()
            logger.info(
                f"[ai_rights] cached for application {application_id} "
                f"(in={result.get('prompt_tokens')}, out={result.get('completion_tokens')})"
            )
        return out
    except Exception as e:
        logger.warning(f"[ai_rights] LLM call failed: {e}")
        return _empty_result()
