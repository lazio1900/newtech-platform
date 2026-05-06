from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import time
import random
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ConnectorError(Exception):
    """Base exception for connector errors"""
    pass


class NetworkError(ConnectorError):
    """Network-related errors (retryable)"""
    pass


class AuthenticationError(ConnectorError):
    """Authentication errors (needs token refresh)"""
    pass


class ParserError(ConnectorError):
    """Parser errors (site structure changed)"""
    pass


class RateLimitError(ConnectorError):
    """Rate limit/429 errors"""
    pass


class BrowserError(ConnectorError):
    """Browser automation errors (retryable)"""
    pass


class PageLoadError(BrowserError):
    """Page failed to load within timeout"""
    pass


class ElementNotFoundError(BrowserError):
    """Expected page element not found (site may have changed)"""
    pass


class BaseConnector(ABC):
    """
    Base class for all data connectors
    Provides common functionality: retry logic, rate limiting, error handling
    """

    def __init__(
        self,
        name: str,
        rate_limit_per_minute: int = 60,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ):
        self.name = name
        self.rate_limit_per_minute = rate_limit_per_minute
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.last_request_time: Optional[float] = None

    def _wait_for_rate_limit(self):
        """Enforce rate limiting between requests"""
        if self.last_request_time is None:
            self.last_request_time = time.time()
            return

        min_interval = 60.0 / self.rate_limit_per_minute
        elapsed = time.time() - self.last_request_time
        
        if elapsed < min_interval:
            sleep_time = min_interval - elapsed
            logger.debug(f"{self.name}: Rate limit wait {sleep_time:.2f}s")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()

    def _exponential_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff with jitter"""
        delay = self.base_delay * (2 ** attempt)
        jitter = random.uniform(0, delay * 0.1)
        return delay + jitter

    @abstractmethod
    def fetch(self, **kwargs) -> Dict[str, Any]:
        """
        Fetch data from the source
        
        Returns:
            Dict with keys:
                - 'data': List of raw items
                - 'metadata': Dict with source info, timestamps, etc.
        """
        pass

    @abstractmethod
    def parse(self, raw_data: Any) -> List[Dict[str, Any]]:
        """
        Parse raw data into normalized format
        
        Returns:
            List of normalized data dictionaries
        """
        pass

    def collect(self, **kwargs) -> Dict[str, Any]:
        """
        Main entry point: fetch + parse with retry logic
        
        Returns:
            Dict with keys:
                - 'items': List of normalized items
                - 'metadata': Collection metadata
                - 'raw': Raw data (optional)
        """
        for attempt in range(self.max_retries):
            try:
                self._wait_for_rate_limit()
                
                logger.info(f"{self.name}: Fetching data (attempt {attempt + 1}/{self.max_retries})")
                raw_result = self.fetch(**kwargs)
                
                logger.info(f"{self.name}: Parsing data")
                items = self.parse(raw_result['data'])
                
                return {
                    'items': items,
                    'metadata': {
                        **raw_result.get('metadata', {}),
                        'fetched_at': datetime.utcnow().isoformat(),
                        'connector': self.name,
                        'attempt': attempt + 1,
                    },
                    'raw': raw_result.get('data'),
                }
            
            except (NetworkError, RateLimitError, BrowserError) as e:
                logger.warning(f"{self.name}: Retryable error on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    delay = self._exponential_backoff(attempt)
                    logger.info(f"{self.name}: Retrying in {delay:.2f}s")
                    time.sleep(delay)
                else:
                    logger.error(f"{self.name}: Max retries exceeded")
                    raise
            
            except (AuthenticationError, ParserError) as e:
                logger.error(f"{self.name}: Non-retryable error: {e}")
                raise
            
            except Exception as e:
                logger.exception(f"{self.name}: Unexpected error: {e}")
                raise ConnectorError(f"Unexpected error: {e}")

        raise ConnectorError("Collection failed after all retries")
