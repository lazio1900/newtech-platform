"""
KB부동산 API endpoint discovery tool.

Playwright를 사용하여 kbland.kr을 탐색하고,
프론트엔드가 호출하는 내부 API 엔드포인트를 자동으로 캡처합니다.
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs

from playwright.async_api import Page, Response, Request

from browser.session_manager import BrowserSessionManager
from browser.stealth import get_random_delay

logger = logging.getLogger(__name__)

# KB부동산 관련 API 도메인
KB_API_DOMAINS = [
    "data-api.kbland.kr",
    "api.kbland.kr",
    "kbland.kr/api",
]


class CapturedRequest:
    """캡처된 API 요청/응답 정보"""

    def __init__(self):
        self.url: str = ""
        self.method: str = ""
        self.headers: Dict[str, str] = {}
        self.post_data: Optional[str] = None
        self.status: Optional[int] = None
        self.response_headers: Dict[str, str] = {}
        self.response_body: Optional[Any] = None
        self.response_body_preview: Optional[str] = None
        self.timestamp: str = datetime.utcnow().isoformat()
        self.category: str = "unknown"

    def to_dict(self) -> dict:
        parsed = urlparse(self.url)
        return {
            "url": self.url,
            "method": self.method,
            "domain": parsed.netloc,
            "path": parsed.path,
            "query_params": parse_qs(parsed.query),
            "post_data": self.post_data,
            "status": self.status,
            "request_headers": self.headers,
            "response_body_preview": self.response_body_preview,
            "category": self.category,
            "timestamp": self.timestamp,
        }


class KBApiDiscovery:
    """
    kbland.kr 내부 API 엔드포인트 자동 발견 도구.

    사용법:
        discovery = KBApiDiscovery()
        report = await discovery.discover()
        print(json.dumps(report, indent=2, ensure_ascii=False))
    """

    def __init__(self):
        self._captured: List[CapturedRequest] = []

    def _is_api_request(self, url: str) -> bool:
        """KB API 도메인으로의 요청인지 확인"""
        return any(domain in url for domain in KB_API_DOMAINS)

    def _on_request(self, request: Request) -> None:
        """네트워크 요청 캡처"""
        url = request.url
        if not self._is_api_request(url):
            return

        captured = CapturedRequest()
        captured.url = url
        captured.method = request.method
        captured.headers = dict(request.headers)
        captured.post_data = request.post_data
        self._captured.append(captured)

        logger.debug(f"Captured request: {request.method} {url}")

    async def _on_response(self, response: Response) -> None:
        """네트워크 응답 캡처"""
        url = response.url
        if not self._is_api_request(url):
            return

        # 매칭되는 요청 찾기
        for captured in reversed(self._captured):
            if captured.url == url and captured.status is None:
                captured.status = response.status
                captured.response_headers = dict(response.headers)
                try:
                    body = await response.json()
                    captured.response_body = body
                    # 미리보기용으로 축약
                    body_str = json.dumps(body, ensure_ascii=False)
                    captured.response_body_preview = body_str[:2000]
                except Exception:
                    try:
                        text = await response.text()
                        captured.response_body_preview = text[:2000]
                    except Exception:
                        captured.response_body_preview = "(failed to read body)"

                logger.debug(f"Captured response: {response.status} {url}")
                break

    def _categorize(self, captured: CapturedRequest) -> str:
        """API 요청을 카테고리로 분류"""
        url_lower = captured.url.lower()
        path = urlparse(captured.url).path.lower()
        post_data = (captured.post_data or "").lower()

        # 단지 검색/목록
        if any(k in path for k in ["complex", "hscm", "danji", "search"]):
            return "complex_search"

        # 시세 (가격)
        if any(k in path for k in ["price", "sise", "pric", "dealamt"]):
            return "price"
        if any(k in url_lower for k in ["priceindex", "avgprice", "medianprice"]):
            return "price_statistics"

        # 실거래가
        if any(k in path for k in ["deal", "trade", "transaction", "silgeorae"]):
            return "transaction"

        # 매물
        if any(k in path for k in ["article", "maemul", "listing", "sale"]):
            return "listing"

        # 지역/법정동
        if any(k in path for k in ["region", "area", "dong", "lawd", "sido"]):
            return "region"

        # 통계
        if any(k in path for k in ["stat", "trend", "index"]):
            return "statistics"

        return "other"

    async def discover(
        self,
        complex_url: Optional[str] = None,
        wait_seconds: float = 5.0,
    ) -> Dict[str, Any]:
        """
        API 엔드포인트 전체 발견 실행.

        Args:
            complex_url: 특정 단지 페이지 URL (없으면 메인에서 시작)
            wait_seconds: 각 페이지에서 API 응답 대기 시간

        Returns:
            발견된 엔드포인트를 카테고리별로 분류한 리포트
        """
        self._captured.clear()

        session = await BrowserSessionManager.get_instance()
        page = await session.new_page()

        try:
            # 이벤트 리스너 등록
            page.on("request", self._on_request)
            page.on("response", self._on_response)

            # Step 1: 메인 페이지 접속
            logger.info("Step 1: Navigating to kbland.kr main page")
            await page.goto("https://kbland.kr", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(get_random_delay(2.0, 4.0))

            # Step 2: 지도 페이지 이동
            logger.info("Step 2: Navigating to map page")
            await page.goto("https://kbland.kr/map", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(get_random_delay(3.0, wait_seconds))

            # Step 3: 특정 단지 페이지가 지정된 경우 이동
            if complex_url:
                logger.info(f"Step 3: Navigating to complex page: {complex_url}")
                await page.goto(complex_url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(get_random_delay(3.0, wait_seconds))

                # 시세, 실거래가, 매물 탭을 순차적으로 클릭 시도
                await self._try_click_tabs(page)

            # Step 4: 결과 분류 및 리포트 생성
            return self._generate_report()

        finally:
            await page.close()

    async def _try_click_tabs(self, page: Page) -> None:
        """단지 상세 페이지에서 시세/실거래가/매물 탭 클릭 시도"""
        tab_selectors = [
            # 시세 관련
            ('text="시세"', "price"),
            ('text="KB시세"', "price"),
            ('[class*="price"]', "price"),
            # 실거래가 관련
            ('text="실거래가"', "transaction"),
            ('text="실거래"', "transaction"),
            ('[class*="deal"]', "transaction"),
            # 매물 관련
            ('text="매물"', "listing"),
            ('text="호가"', "listing"),
            ('[class*="article"]', "listing"),
        ]

        for selector, category in tab_selectors:
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=2000):
                    logger.info(f"Clicking tab: {selector} (category: {category})")
                    await element.click()
                    await asyncio.sleep(get_random_delay(2.0, 4.0))
            except Exception:
                pass  # 해당 탭이 없을 수 있음

    def _generate_report(self) -> Dict[str, Any]:
        """캡처된 요청을 분류하여 리포트 생성"""
        # 카테고리 분류
        for captured in self._captured:
            captured.category = self._categorize(captured)

        # 카테고리별 그룹핑
        categorized: Dict[str, List[dict]] = {}
        for captured in self._captured:
            cat = captured.category
            if cat not in categorized:
                categorized[cat] = []
            categorized[cat].append(captured.to_dict())

        # 유니크 엔드포인트 추출
        unique_endpoints: Dict[str, dict] = {}
        for captured in self._captured:
            parsed = urlparse(captured.url)
            key = f"{captured.method} {parsed.netloc}{parsed.path}"
            if key not in unique_endpoints:
                unique_endpoints[key] = {
                    "method": captured.method,
                    "domain": parsed.netloc,
                    "path": parsed.path,
                    "category": captured.category,
                    "sample_params": parse_qs(parsed.query),
                    "sample_post_data": captured.post_data,
                    "sample_status": captured.status,
                    "hit_count": 0,
                }
            unique_endpoints[key]["hit_count"] += 1

        return {
            "discovery_timestamp": datetime.utcnow().isoformat(),
            "total_requests_captured": len(self._captured),
            "unique_endpoints": len(unique_endpoints),
            "endpoints_by_category": categorized,
            "unique_endpoint_summary": list(unique_endpoints.values()),
        }
