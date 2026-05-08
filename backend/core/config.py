from typing import List, Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ----- Environment -----
    environment: Literal["development", "staging", "production"] = "development"

    # ----- Database / Redis -----
    database_url: str = "postgresql://kb_user:kb_password@localhost:5433/kb_estate"
    redis_url: str = "redis://localhost:6379/0"

    # ----- API server -----
    api_host: str = "0.0.0.0"
    api_port: int = 8002

    # ----- CORS (comma-separated) -----
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    def get_cors_origins(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # ----- JWT (Phase 1b에서 사용) -----
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    # ----- LLM / OpenAI (Phase 3에서 사용) -----
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o"
    llm_max_tokens: int = 4096
    llm_timeout_seconds: int = 60
    llm_daily_call_limit: int = 1000

    # ----- 등기부등본 API (별도 마이크로서비스, 8100 포트) -----
    registry_api_url: str = "http://localhost:8100"
    registry_internal_token: Optional[str] = None
    registry_request_timeout: int = 60

    # ----- Logging / Observability -----
    log_level: str = "INFO"
    log_format: str = "json"
    sentry_dsn: Optional[str] = None

    # ----- Rate limiting -----
    default_rate_limit_per_minute: int = 60

    # ----- Object storage (Phase 2 첨부파일) -----
    s3_endpoint: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_bucket: str = "newtech-uploads"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


settings = Settings()


def assert_production_safe() -> None:
    """운영 환경에서 위험한 기본값이 남아있는지 검사. 미설정 시 startup 실패."""
    if not settings.is_production:
        return
    issues = []
    if "change-me" in settings.jwt_secret_key:
        issues.append("JWT_SECRET_KEY must be set in production")
    if "kb_password" in settings.database_url:
        issues.append("DATABASE_URL must not use the default password in production")
    cors_list = settings.get_cors_origins()
    if "*" in cors_list or not cors_list:
        issues.append("CORS_ORIGINS must be a domain whitelist in production")
    if issues:
        raise RuntimeError("Insecure configuration:\n - " + "\n - ".join(issues))
