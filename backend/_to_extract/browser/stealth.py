"""
Anti-detection utilities for browser automation.
Reduces the chance of being identified as an automated browser.
"""
import random
from typing import List

USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
]


def get_random_user_agent() -> str:
    """Return a random modern Chrome user agent string."""
    return random.choice(USER_AGENTS)


def get_random_delay(min_seconds: float = 1.0, max_seconds: float = 5.0) -> float:
    """Human-like random delay between actions."""
    return random.uniform(min_seconds, max_seconds)


STEALTH_INIT_SCRIPT = """
// Override webdriver detection
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});

// Override plugins (headless Chrome has empty plugins)
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5]
});

// Override languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['ko-KR', 'ko', 'en-US', 'en']
});

// Override Chrome runtime
window.chrome = {
    runtime: {},
};

// Override permissions query
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);
"""


async def apply_stealth_scripts(page) -> None:
    """Inject JavaScript to mask automation indicators."""
    await page.add_init_script(STEALTH_INIT_SCRIPT)
