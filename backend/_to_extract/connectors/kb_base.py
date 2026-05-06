"""
KB부동산 전용 하이브리드 베이스 커넥터.

전략:
1. 먼저 httpx로 직접 API 호출 시도 (빠르고 가벼움)
2. 연속 실패 시 Playwright 브라우저 폴백 (느리지만 확실함)
"""
import asyncio
import random
import logging
from abc import abstractmethod
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from connectors.base import (
    BaseConnector,
    NetworkError,
    AuthenticationError,
    RateLimitError,
    BrowserError,
    PageLoadError,
)
from connectors.kb_endpoints import KBEndpoint
from browser.session_manager import BrowserSessionManager
from browser.stealth import get_random_delay
from core.config import settings

logger = logging.getLogger(__name__)


class KBBaseConnector(BaseConnector):
    """
    KB부동산 커넥터의 공통 베이스 클래스.

    상속 구조:
        BaseConnector (base.py)
            -> KBBaseConnector (이 파일) — 하이브리드 HTTP/Browser
                -> KBPriceConnector
                -> KBTransactionConnector
                -> KBListingConnector
    """

    def __init__(
        self,
        name: str,
        rate_limit_per_minute: int = 20,
        max_retries: int = 3,
        db_session=None,
    ):
        super().__init__(
            name=name,
            rate_limit_per_minute=rate_limit_per_minute,
            max_retries=max_retries,
        )
        self._db_session = db_session
        self._http_client: Optional[httpx.AsyncClient] = None
        self._use_browser_fallback: bool = False
        self._consecutive_http_failures: int = 0
        self._max_http_failures_before_fallback: int = 3

    @property
    def db(self):
        if self._db_session is None:
            raise ValueError(f"{self.name}: DB session required but not provided")
        return self._db_session

    def _get_default_headers(self) -> dict:
        """브라우저처럼 보이는 기본 HTTP 헤더"""
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Referer": "https://kbland.kr/map",
            "Origin": "https://kbland.kr",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "webservice": "1",
        }

    async def _get_http_client(self) -> httpx.AsyncClient:
        """HTTP 클라이언트 lazy 초기화"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                headers=self._get_default_headers(),
                timeout=30.0,
                follow_redirects=True,
                http2=True,
            )
        return self._http_client

    async def _fetch_via_http(self, endpoint: KBEndpoint, params: dict) -> dict:
        """httpx를 사용한 직접 API 호출"""
        client = await self._get_http_client()

        logger.debug(f"{self.name}: HTTP {endpoint.method} {endpoint.url}")

        if endpoint.method == "GET":
            response = await client.get(endpoint.url, params=params)
        else:
            response = await client.post(endpoint.url, json=params)

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            raise RateLimitError(f"Rate limited: {response.status_code}")
        elif response.status_code in (401, 403):
            raise AuthenticationError(f"Auth error: {response.status_code}")
        else:
            raise NetworkError(
                f"HTTP {response.status_code}: {response.text[:300]}"
            )

    async def _fetch_via_browser(
        self,
        page_url: str,
        api_url_pattern: str,
        interaction_fn: Optional[Callable] = None,
    ) -> dict:
        """
        Playwright 브라우저 폴백.
        페이지 탐색 → API 응답 인터셉트.
        """
        session = await BrowserSessionManager.get_instance()
        page = await session.new_page()

        try:
            timeout = settings.browser_timeout_ms

            # 페이지 이동
            logger.info(f"{self.name}: Browser navigating to {page_url}")
            await page.goto(page_url, wait_until="networkidle", timeout=timeout)

            # 랜덤 딜레이 (봇 감지 방지)
            delay = get_random_delay(settings.min_request_delay, settings.max_request_delay)
            await asyncio.sleep(delay)

            # API 응답 대기하며 인터랙션 수행
            async with page.expect_response(
                lambda r: api_url_pattern in r.url and r.status == 200,
                timeout=15000,
            ) as response_info:
                if interaction_fn:
                    await interaction_fn(page)
                else:
                    # 일부 페이지는 자동으로 데이터를 로드
                    await asyncio.sleep(2.0)

            response = await response_info.value
            data = await response.json()
            return data

        except Exception as e:
            raise PageLoadError(f"Browser fetch failed: {e}") from e
        finally:
            await page.close()

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """
        동기 fetch 래퍼. BaseConnector.collect()에서 호출됨.
        내부적으로 async 하이브리드 fetch를 실행.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 이미 이벤트 루프가 실행 중인 경우 (Celery 등)
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(asyncio.run, self._async_fetch(**kwargs)).result()
                return result
            else:
                return loop.run_until_complete(self._async_fetch(**kwargs))
        except RuntimeError:
            # 이벤트 루프가 없는 경우
            return asyncio.run(self._async_fetch(**kwargs))

    async def _async_fetch(self, **kwargs) -> Dict[str, Any]:
        """
        하이브리드 fetch: HTTP 우선 → 브라우저 폴백.
        """
        endpoint, params = self._build_http_params(**kwargs)

        if not self._use_browser_fallback:
            try:
                data = await self._fetch_via_http(endpoint, params)
                self._consecutive_http_failures = 0
                logger.info(f"{self.name}: HTTP direct fetch succeeded")
                return {
                    "data": data,
                    "metadata": {"method": "http_direct", "source": "kb"},
                }
            except (AuthenticationError, NetworkError) as e:
                self._consecutive_http_failures += 1
                logger.warning(
                    f"{self.name}: HTTP failed ({self._consecutive_http_failures}/"
                    f"{self._max_http_failures_before_fallback}): {e}"
                )
                if self._consecutive_http_failures >= self._max_http_failures_before_fallback:
                    logger.warning(f"{self.name}: Switching to browser fallback")
                    self._use_browser_fallback = True
                else:
                    raise

        # 브라우저 폴백
        page_url, api_pattern, interaction = self._build_browser_config(**kwargs)
        data = await self._fetch_via_browser(page_url, api_pattern, interaction)
        logger.info(f"{self.name}: Browser fallback fetch succeeded")
        return {
            "data": data,
            "metadata": {"method": "browser_intercept", "source": "kb"},
        }

    def _resolve_kb_complex_id(self, complex_id: int) -> str:
        """DB에서 KB 단지 ID 조회"""
        from models.complex import Complex
        complex_obj = self.db.query(Complex).get(complex_id)
        if not complex_obj or not complex_obj.kb_complex_id:
            raise ValueError(f"Complex {complex_id}: kb_complex_id not found")
        return complex_obj.kb_complex_id

    def _resolve_kb_ids(self, complex_id: int, area_id: int) -> Tuple[str, str]:
        """DB에서 KB 단지 ID + 면적 코드 조회"""
        from models.complex import Complex, Area
        complex_obj = self.db.query(Complex).get(complex_id)
        area_obj = self.db.query(Area).get(area_id)

        if not complex_obj or not complex_obj.kb_complex_id:
            raise ValueError(f"Complex {complex_id}: kb_complex_id not found")
        if not area_obj or not area_obj.kb_area_code:
            raise ValueError(f"Area {area_id}: kb_area_code not found")

        return (complex_obj.kb_complex_id, area_obj.kb_area_code)

    @staticmethod
    def _to_won(amount_man) -> Optional[int]:
        """만원 단위 가격 파싱 (KB API 원본 단위 그대로 저장)"""
        if amount_man is None:
            return None
        try:
            if isinstance(amount_man, str):
                amount_man = int(amount_man.replace(",", "").strip())
            return int(amount_man)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_date(date_str: str) -> Optional[str]:
        """YYYYMMDD → YYYY-MM-DD 변환"""
        if not date_str:
            return None
        date_str = date_str.strip()
        if len(date_str) == 8:
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        return date_str

    @abstractmethod
    def _build_http_params(self, **kwargs) -> Tuple[KBEndpoint, dict]:
        """직접 HTTP 호출용 (엔드포인트, 파라미터) 반환. 하위 클래스에서 구현."""
        ...

    @abstractmethod
    def _build_browser_config(self, **kwargs) -> Tuple[str, str, Optional[Callable]]:
        """브라우저 폴백용 (page_url, api_url_pattern, interaction_fn) 반환."""
        ...

    async def close(self):
        """HTTP 클라이언트 정리"""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None
