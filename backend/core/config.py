from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql://kb_user:kb_password@localhost:5433/kb_estate"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_key: str = "dev-api-key"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    # Object Storage (Optional)
    s3_endpoint: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_bucket: str = "kb-estate-raw-data"

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Rate Limiting
    default_rate_limit_per_minute: int = 60
    kb_rate_limit_per_minute: int = 20

    # Browser / Crawling
    browser_headless: bool = True
    browser_timeout_ms: int = 30000
    min_request_delay: float = 2.0
    max_request_delay: float = 5.0

    # Notification
    slack_webhook_url: Optional[str] = None
    sentry_dsn: Optional[str] = None


settings = Settings()
