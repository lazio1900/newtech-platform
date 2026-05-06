"""
KB 실거래가 데이터 수집 커넥터.

KB부동산에서 아파트 단지별 실거래가 데이터를 수집합니다.
기존 MolitTransactionConnector(국토교통부 OpenAPI)와 독립적으로 동작합니다.
"""
from typing import Any, Callable, Dict, List, Optional, Tuple
import logging

from connectors.kb_base import KBBaseConnector
from connectors.kb_endpoints import KBEndpoint, COMPLEX_TRANSACTION
from connectors.base import ParserError

logger = logging.getLogger(__name__)


class KBTransactionConnector(KBBaseConnector):
    """
    KB 실거래가 커넥터.

    수집 데이터: 계약일, 거래가, 전용면적, 층, 해제여부
    단위: 만원 (KB API 원본 단위 그대로 저장)
    """

    def __init__(self, db_session=None, rate_limit_per_minute: int = 20):
        super().__init__(
            name="KBTransactionConnector",
            rate_limit_per_minute=rate_limit_per_minute,
            db_session=db_session,
        )

    def _build_http_params(self, **kwargs) -> Tuple[KBEndpoint, dict]:
        """실거래가 API 직접 호출용 파라미터 빌드"""
        complex_id = kwargs["complex_id"]
        area_id = kwargs.get("area_id")
        kb_complex_id = self._resolve_kb_complex_id(complex_id)

        params = {
            "단지기본일련번호": kb_complex_id,
            "거래유형": "1",  # 1=매매
        }
        if area_id:
            from models.complex import Area
            area_obj = self.db.query(Area).get(area_id)
            if area_obj and area_obj.kb_area_code:
                params["면적일련번호"] = area_obj.kb_area_code
        return (COMPLEX_TRANSACTION, params)

    def _build_browser_config(self, **kwargs) -> Tuple[str, str, Optional[Callable]]:
        """실거래가 브라우저 폴백 설정"""
        complex_id = kwargs["complex_id"]
        kb_complex_id = self._resolve_kb_complex_id(complex_id)

        page_url = f"https://kbland.kr/map?complexNo={kb_complex_id}"
        api_pattern = "deal"

        async def interact(page):
            """실거래가 탭 클릭"""
            tab_selectors = [
                'text="실거래가"',
                'text="실거래"',
                '[data-tab="deal"]',
                'button:has-text("실거래")',
            ]
            for selector in tab_selectors:
                try:
                    el = page.locator(selector).first
                    if await el.is_visible(timeout=2000):
                        await el.click()
                        await page.wait_for_timeout(2000)
                        return
                except Exception:
                    continue

        return (page_url, api_pattern, interact)

    def parse(self, raw_data: Any) -> List[Dict[str, Any]]:
        """
        KB 실거래가 응답 파싱.

        응답 구조 (API 디스커버리 후 확정 필요):
        {
            "dataBody": {
                "data": {
                    "dealList": [
                        {
                            "dealDate": "20241215",
                            "dealAmt": "50,000",       # 만원
                            "excArea": "84.50",
                            "floor": "10",
                            "cancelYn": "N",
                        },
                        ...
                    ]
                }
            }
        }
        """
        try:
            # 응답 구조 탐색
            data = raw_data
            if isinstance(data, dict):
                data = data.get("dataBody", data)
                if isinstance(data, dict):
                    data = data.get("data", data)

            # 거래 목록 추출 (여러 후보 키)
            deal_list = []
            if isinstance(data, dict):
                for key in ["dealList", "list", "items", "tradeList", "거래목록"]:
                    if key in data and isinstance(data[key], list):
                        deal_list = data[key]
                        break
            elif isinstance(data, list):
                deal_list = data

            parsed = []
            for item in deal_list:
                if not isinstance(item, dict):
                    continue

                # 계약일
                contract_date = self._extract_date(item)

                # 거래가
                price = self._extract_transaction_price(item)

                # 전용면적
                exclusive_m2 = self._extract_float(
                    item, ["excArea", "exclusive_m2", "전용면적", "exclusiveArea"]
                )

                # 층
                floor = self._extract_int(item, ["floor", "층", "floorInfo"])

                # 해제 여부
                is_cancelled = self._extract_cancel_status(item)

                if contract_date and price:
                    parsed.append({
                        "contract_date": contract_date,
                        "price": price,
                        "exclusive_m2": exclusive_m2 or 0.0,
                        "floor": floor,
                        "is_cancelled": is_cancelled,
                        "source": "kb",
                    })

            return parsed

        except Exception as e:
            raise ParserError(f"Failed to parse KB transaction data: {e}")

    def _extract_date(self, item: dict) -> Optional[str]:
        """거래 항목에서 날짜 추출"""
        # 단일 날짜 필드
        for key in ["dealDate", "contract_date", "거래일", "계약일", "tradeDate"]:
            if key in item and item[key]:
                return self._parse_date(str(item[key]))

        # 년/월/일 분리된 필드
        year = item.get("년") or item.get("year") or item.get("dealYear")
        month = item.get("월") or item.get("month") or item.get("dealMonth")
        day = item.get("일") or item.get("day") or item.get("dealDay")
        if year and month:
            day = day or "1"
            return f"{str(year).zfill(4)}-{str(month).zfill(2)}-{str(day).zfill(2)}"

        return None

    def _extract_transaction_price(self, item: dict) -> Optional[int]:
        """거래가 추출 (만원 단위)"""
        for key in ["dealAmt", "price", "거래금액", "거래가", "tradeAmt"]:
            if key in item and item[key] is not None:
                return self._to_won(item[key])
        return None

    @staticmethod
    def _extract_float(item: dict, keys: List[str]) -> Optional[float]:
        """여러 후보 키에서 float 추출"""
        for key in keys:
            if key in item and item[key] is not None:
                try:
                    return float(str(item[key]).replace(",", "").strip())
                except (ValueError, TypeError):
                    continue
        return None

    @staticmethod
    def _extract_int(item: dict, keys: List[str]) -> Optional[int]:
        """여러 후보 키에서 int 추출"""
        for key in keys:
            if key in item and item[key] is not None:
                try:
                    return int(str(item[key]).replace(",", "").strip())
                except (ValueError, TypeError):
                    continue
        return None

    @staticmethod
    def _extract_cancel_status(item: dict) -> bool:
        """해제 여부 추출"""
        for key in ["cancelYn", "is_cancelled", "해제여부", "cancelDealYn"]:
            if key in item:
                val = str(item[key]).strip().upper()
                return val in ("Y", "TRUE", "1", "해제")
        return False
