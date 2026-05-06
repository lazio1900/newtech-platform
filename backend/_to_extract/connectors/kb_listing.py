"""
KB 매물/호가 데이터 수집 커넥터.

KB부동산에서 아파트 단지별 매물 정보를 수집합니다.
개인정보(연락처 등)는 수집하지 않습니다.

API 흐름:
1. GET /land-complex/complex/brif?단지기본일련번호={id} → 단지 브리프
2. POST /land-property/propList/main (body: brif + 페이지 파라미터) → 매물 목록
"""
from typing import Any, Callable, Dict, List, Optional, Tuple
import logging
import math

import httpx

from connectors.kb_base import KBBaseConnector
from connectors.kb_endpoints import KBEndpoint, COMPLEX_BRIF, COMPLEX_PROP_LIST
from connectors.base import ParserError, NetworkError

logger = logging.getLogger(__name__)

# 매물 상태 매핑 (KB 매물상태구분 → 내부 상태)
STATUS_MAP = {
    "1": "active",    # 등록대기
    "2": "active",    # 등록중
    "3": "sold",      # 거래완료
    "4": "removed",   # 삭제
    "5": "removed",   # 기간만료
}

PAGE_SIZE = 50  # 한 페이지에 요청할 매물 수 (최대 50)


class KBListingConnector(KBBaseConnector):
    """
    KB 매물/호가 커넥터.

    수집 데이터: 매물ID, 호가, 전용면적, 층, 상태, 등록일
    주의: 공개된 호가 정보만 수집, 개인정보(연락처) 수집 금지
    """

    def __init__(self, db_session=None, rate_limit_per_minute: int = 20):
        super().__init__(
            name="KBListingConnector",
            rate_limit_per_minute=rate_limit_per_minute,
            db_session=db_session,
        )

    def _build_http_params(self, **kwargs) -> Tuple[KBEndpoint, dict]:
        """propList/main은 2단계 API이므로 여기선 brif 엔드포인트만 반환."""
        kb_complex_id = kwargs.get("kb_complex_id") or self._resolve_kb_complex_id(kwargs["complex_id"])
        return (COMPLEX_BRIF, {"단지기본일련번호": kb_complex_id})

    def _build_browser_config(self, **kwargs) -> Tuple[str, str, Optional[Callable]]:
        """매물 브라우저 폴백 설정"""
        kb_complex_id = kwargs.get("kb_complex_id") or self._resolve_kb_complex_id(kwargs["complex_id"])
        page_url = f"https://kbland.kr/pl/{kb_complex_id}"
        api_pattern = "propList/main"
        return (page_url, api_pattern, None)

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """
        동기 2단계 fetch: brif GET → propList/main POST (전체 페이지 순회).
        async event loop 문제를 피하기 위해 동기 httpx.Client 사용.
        """
        kb_complex_id = kwargs.get("kb_complex_id") or self._resolve_kb_complex_id(kwargs["complex_id"])

        with httpx.Client(
            headers=self._get_default_headers(),
            http2=True,
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            # Step 1: GET brif
            logger.info(f"{self.name}: GET brif for complex {kb_complex_id}")
            brif_resp = client.get(COMPLEX_BRIF.url, params={"단지기본일련번호": kb_complex_id})
            if brif_resp.status_code != 200:
                raise NetworkError(f"brif HTTP {brif_resp.status_code}")
            brif_data = brif_resp.json().get("dataBody", {}).get("data", {})
            logger.info(f"{self.name}: brif keys={list(brif_data.keys())[:20]}")
            if not brif_data:
                raise NetworkError(f"brif returned empty data for {kb_complex_id}")

            total_listings = (brif_data.get("매매건수") or 0) + (brif_data.get("전세건수") or 0) + (brif_data.get("월세건수") or 0)
            logger.info(f"{self.name}: {brif_data.get('단지명')} - 매매:{brif_data.get('매매건수')} 전세:{brif_data.get('전세건수')} 월세:{brif_data.get('월세건수')}")

            if total_listings == 0:
                return {"data": {"propertyList": []}, "metadata": {"method": "http_direct", "source": "kb"}}

            # Step 2: POST propList/main (모든 페이지)
            all_items = []
            total_pages = max(1, math.ceil(total_listings / PAGE_SIZE))

            for page_no in range(1, total_pages + 1):
                post_body = {
                    **brif_data,
                    "페이지번호": page_no,
                    "페이지목록수": PAGE_SIZE,
                    "중복타입": "02",
                    "정렬타입": "date",
                    "매물거래구분": "",
                    "면적일련번호": "",
                    "전자계약여부": "0",
                    "비대면대출여부": "0",
                    "클린주택여부": "0",
                    "honeyYn": "0",
                }

                prop_resp = client.post(COMPLEX_PROP_LIST.url, json=post_body)
                if prop_resp.status_code != 200:
                    logger.warning(f"{self.name}: propList page {page_no} HTTP {prop_resp.status_code}")
                    break

                prop_data = prop_resp.json().get("dataBody", {}).get("data", {})
                items = prop_data.get("propertyList", [])
                if not items:
                    break

                all_items.extend(items)

                # 서버가 알려주는 실제 총 페이지수 반영
                server_pages = prop_data.get("페이지개수")
                if server_pages and page_no >= int(server_pages):
                    break

        logger.info(f"{self.name}: Fetched {len(all_items)} listings for {brif_data.get('단지명')}")

        # brif_data에서 주소 추출 - 여러 전략 시도
        complex_address = ""
        # 1) 단일 주소 필드
        for key in ["도로명주소", "소재지도로명주소", "주소", "소재지주소", "법정동주소",
                     "단지주소", "roadAddr", "addrNm", "address", "addr"]:
            if key in brif_data and brif_data[key]:
                complex_address = str(brif_data[key]).strip()
                break
        # 2) 컴포넌트 조합
        if not complex_address:
            parts = []
            for key in ["시도명", "시군구명", "법정동명"]:
                val = brif_data.get(key, "")
                if val:
                    parts.append(str(val).strip())
            if parts:
                complex_address = " ".join(parts)
        # 3) "주소" 또는 "addr"가 포함된 키 탐색
        if not complex_address:
            for key, val in brif_data.items():
                if ("주소" in str(key) or "addr" in str(key).lower()) and val:
                    val_str = str(val).strip()
                    if len(val_str) >= 4:
                        complex_address = val_str
                        break

        if not complex_address:
            logger.warning(f"{self.name}: no address found in brif_data")

        return {
            "data": {"propertyList": all_items, "총매물건수": len(all_items)},
            "metadata": {
                "method": "http_direct",
                "source": "kb",
                "complex_address": complex_address,
                "complex_name": brif_data.get("단지명", ""),
            },
        }

    def parse(self, raw_data: Any) -> List[Dict[str, Any]]:
        """
        KB 매물 응답 파싱.
        개인정보(연락처, 중개사 정보 등)는 의도적으로 수집하지 않음.
        """
        try:
            data = raw_data
            if isinstance(data, dict):
                # dataBody.data.propertyList or data.propertyList
                data = data.get("dataBody", data)
                if isinstance(data, dict):
                    data = data.get("data", data)

            prop_list = []
            if isinstance(data, dict):
                prop_list = data.get("propertyList", [])
            elif isinstance(data, list):
                prop_list = data

            parsed = []
            seen_ids = set()
            for item in prop_list:
                if not isinstance(item, dict):
                    continue
                listing = self._parse_single_listing(item)
                if listing and listing["source_listing_id"] not in seen_ids:
                    seen_ids.add(listing["source_listing_id"])
                    parsed.append(listing)

            return parsed

        except Exception as e:
            raise ParserError(f"Failed to parse KB listing data: {e}")

    def _parse_single_listing(self, item: dict) -> Optional[Dict[str, Any]]:
        """단일 매물 항목 파싱 (개인정보 필터링 포함)"""
        # 매물 ID
        listing_id = item.get("매물일련번호")
        if not listing_id:
            return None
        listing_id = f"KB{listing_id}"

        # 호가 (만원 단위)
        ask_price = None
        for key in ["매매가", "최소매매가", "전세가"]:
            val = item.get(key)
            if val is not None and val != "" and val != "null":
                ask_price = self._to_won(val)
                if ask_price:
                    break
        if not ask_price:
            return None

        # 전용면적 (순전용면적이 더 정확)
        exclusive_m2 = None
        for key in ["순전용면적", "전용면적"]:
            val = item.get(key)
            if val is not None:
                try:
                    exclusive_m2 = float(str(val).replace(",", "").strip())
                except (ValueError, TypeError):
                    pass
                if exclusive_m2:
                    break

        # 층
        floor = None
        floor_str = item.get("해당층수", "")
        if floor_str:
            try:
                floor = int(str(floor_str).replace("층", "").replace(",", "").strip())
            except (ValueError, TypeError):
                pass

        # 상태
        status_code = str(item.get("매물상태구분", ""))
        status = STATUS_MAP.get(status_code, "active")

        # 등록일
        posted_at = None
        reg_date = item.get("등록년월일", "")
        if reg_date:
            # "2026.02.07" format
            posted_at = reg_date.replace(".", "-") if "." in reg_date else self._parse_date(reg_date)

        # 거래유형
        trade_type = item.get("매물거래구분명", "매매")  # 매매, 전세, 월세

        return {
            "source_listing_id": listing_id,
            "ask_price": ask_price,
            "exclusive_m2": exclusive_m2,
            "floor": floor,
            "status": status,
            "posted_at": posted_at,
            "source": "kb",
            "trade_type": trade_type,
        }
