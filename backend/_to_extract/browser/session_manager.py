"""
Browser session manager for Playwright.
Manages browser lifecycle with anti-detection measures.
"""
import asyncio
import logging
from typing import Optional

from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page

from browser.stealth import get_random_user_agent, apply_stealth_scripts
from core.config import settings

logger = logging.getLogger(__name__)


class BrowserSessionManager:
    """
    Manages Playwright browser lifecycle.
    Singleton per process to share a browser context across tasks.
    """

    _instance: Optional["BrowserSessionManager"] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._is_initialized: bool = False

    @classmethod
    async def get_instance(cls) -> "BrowserSessionManager":
        """Singleton accessor — one browser per worker process."""
        async with cls._lock:
            if cls._instance is None or not cls._instance._is_initialized:
                cls._instance = cls()
                await cls._instance._initialize()
            return cls._instance

    async def _initialize(self):
        """Launch browser with stealth settings."""
        logger.info("Initializing Playwright browser session")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=settings.browser_headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            user_agent=get_random_user_agent(),
            extra_http_headers={
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
            },
        )
        self._is_initialized = True
        logger.info("Browser session initialized successfully")

    async def new_page(self) -> Page:
        """Create a new page with stealth scripts applied."""
        if not self._is_initialized or self._context is None:
            raise RuntimeError("BrowserSessionManager not initialized")
        page = await self._context.new_page()
        await apply_stealth_scripts(page)
        return page

    async def close(self):
        """Cleanly shut down browser and playwright."""
        logger.info("Closing browser session")
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._is_initialized = False

    @classmethod
    async def shutdown(cls):
        """Class-level shutdown for worker process cleanup."""
        if cls._instance and cls._instance._is_initialized:
            await cls._instance.close()
            cls._instance = None
            logger.info("Browser session manager shut down")
