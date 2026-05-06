"""
KB 시세 데이터 수집 커넥터.

KB부동산에서 아파트 단지별 시세(일반가/상위평균가/하위평균가)를 수집합니다.
BasePrcInfoNew 응답에서 최근실거래가와 매물건수도 함께 추출합니다.
"""
from typing import Any, Callable, Dict, List, Optional, Tuple
import logging

from connectors.kb_base import KBBaseConnector
from connectors.kb_endpoints import KBEndpoint, COMPLEX_PRICE
from connectors.base import ParserError

logger = logging.getLogger(__name__)


class KBPriceConnector(KBBaseConnector):
    """
    KB 시세 커넥터.

    수집 데이터: 일반가, 상위평균가(상한가), 하위평균가(하한가)
    단위: 만원 (KB API 원본 단위 그대로 저장)
    """

    def __init__(self, db_session=None, rate_limit_per_minute: int = 20):
        super().__init__(
            name="KBPriceConnector",
            rate_limit_per_minute=rate_limit_per_minute,
            db_session=db_session,
        )

    def _build_http_params(self, **kwargs) -> Tuple[KBEndpoint, dict]:
        """시세 API 직접 호출용 파라미터 빌드"""
        complex_id = kwargs["complex_id"]
        area_id = kwargs["area_id"]
        kb_complex_id, kb_area_code = self._resolve_kb_ids(complex_id, area_id)

        params = {
            "단지기본일련번호": kb_complex_id,
            "면적일련번호": kb_area_code,
        }
        return (COMPLEX_PRICE, params)

    def _build_browser_config(self, **kwargs) -> Tuple[str, str, Optional[Callable]]:
        """시세 브라우저 폴백 설정"""
        complex_id = kwargs["complex_id"]
        kb_complex_id = self._resolve_kb_complex_id(complex_id)

        page_url = f"https://kbland.kr/map?complexNo={kb_complex_id}"
        # API 응답 URL에서 price 관련 패턴 매칭
        api_pattern = "price"

        async def interact(page):
            """시세 탭 클릭"""
            tab_selectors = [
                'text="시세"',
                'text="KB시세"',
                '[data-tab="price"]',
                'button:has-text("시세")',
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
        KB 시세 응답 파싱.

        실제 응답 구조 (2026-02-08 검증 완료):
        {
            "dataBody": {
                "data": {
                    "시세": [{
                        "매매일반거래가": 50500,      # 일반가 (만원)
                        "매매상한가": 52500,           # 상한가 (만원)
                        "매매하한가": 48500,           # 하한가 (만원)
                        "시세기준년월일": "20260206",  # 기준일
                        "매매거래금액": 50500,         # 거래금액 (만원)
                        "면적일련번호": 127753,
                        "단지기본일련번호": 12,
                    }]
                }
            }
        }
        """
        try:
            data = raw_data
            if isinstance(data, dict):
                data = data.get("dataBody", data)
                if isinstance(data, dict):
                    data = data.get("data", data)

            # 시세 리스트 추출
            sise_list = []
            if isinstance(data, dict):
                sise_list = data.get("시세", [])
                if not sise_list:
                    # 폴백: 데이터 자체가 시세 정보인 경우
                    sise_list = [data]
            elif isinstance(data, list):
                sise_list = data

            if not sise_list:
                return []

            price_info = sise_list[0] if isinstance(sise_list, list) else {}

            # 날짜 추출
            as_of_date = None
            for date_key in ["시세기준년월일", "baseDate", "as_of_date", "stdDate"]:
                if date_key in price_info and price_info[date_key]:
                    as_of_date = self._parse_date(str(price_info[date_key]))
                    break
            if as_of_date is None:
                from datetime import date
                as_of_date = date.today().isoformat()

            # 가격 추출 (만원 단위)
            general_price = self._extract_price(
                price_info, ["매매일반거래가", "매매거래금액", "dealAmt", "general_price"]
            )
            high_price = self._extract_price(
                price_info, ["매매상한가", "dealAmtUpper", "high_avg_price"]
            )
            low_price = self._extract_price(
                price_info, ["매매하한가", "dealAmtLower", "low_avg_price"]
            )

            return [{
                "as_of_date": as_of_date,
                "general_price": general_price,
                "high_avg_price": high_price,
                "low_avg_price": low_price,
                "source": "kb",
                "parser_version": "2.1",
            }]

        except Exception as e:
            raise ParserError(f"Failed to parse KB price data: {e}")

    def parse_recent_transaction(self, raw_data: Any) -> Optional[Dict[str, Any]]:
        """
        BasePrcInfoNew 응답에서 최근실거래가 추출.

        응답 내 최근실거래가 구조:
        {
            "거래금액": 299500,        # 만원
            "평균거래금액": 308000,     # 만원
            "거래층": "12",
            "계약년월일": "20251114",  # YYYYMMDD
            "실거래매매증감액": 41500
        }
        """
        try:
            data = raw_data
            if isinstance(data, dict):
                data = data.get("dataBody", data)
                if isinstance(data, dict):
                    data = data.get("data", data)

            if not isinstance(data, dict):
                return None

            recent = data.get("최근실거래가", {})
            if not isinstance(recent, dict):
                return None

            contract_date_raw = recent.get("계약년월일")
            price_raw = recent.get("거래금액")

            if not contract_date_raw or not price_raw:
                return None

            contract_date = self._parse_date(str(contract_date_raw))
            price = self._to_won(price_raw)

            if not contract_date or not price:
                return None

            floor = None
            floor_raw = recent.get("거래층")
            if floor_raw is not None:
                try:
                    floor = int(str(floor_raw).strip())
                except (ValueError, TypeError):
                    pass

            return {
                "contract_date": contract_date,
                "price": price,
                "floor": floor,
                "source": "kb",
            }
        except Exception:
            return None

    def parse_listing_counts(self, raw_data: Any) -> Dict[str, int]:
        """
        BasePrcInfoNew 응답에서 매물 건수 추출.

        응답 내 매매건수/전세건수/월세건수 포함.
        """
        try:
            data = raw_data
            if isinstance(data, dict):
                data = data.get("dataBody", data)
                if isinstance(data, dict):
                    data = data.get("data", data)

            if not isinstance(data, dict):
                return {}

            counts = {}
            for key in ["매매건수", "전세건수", "월세건수"]:
                val = data.get(key)
                if val is not None:
                    try:
                        counts[key] = int(val)
                    except (ValueError, TypeError):
                        pass
            return counts
        except Exception:
            return {}

    def _extract_price(self, data: dict, candidate_keys: List[str]) -> Optional[int]:
        """여러 후보 키에서 가격 추출 (만원 단위)"""
        for key in candidate_keys:
            if key in data and data[key] is not None:
                return self._to_won(data[key])
        return None
