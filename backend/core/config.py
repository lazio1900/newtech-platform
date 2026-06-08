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

    # ----- 데이터 소스 모드 (사내 이관) -----
    # dev  = 외부에서 크롤/PDF 데이터를 내부형식(CCTR_*/nice_rles_*)으로 정형화해 테스트.
    #        개발 전용 적재 스크립트(build_cctr_from_crawl·cctr_to_app --apply·load_nice_*) 허용.
    # prod = 폐쇄망. 내부형식 원천은 Oracle, 적재 주체는 수집기. 개발 적재 스크립트는 거부.
    # 앱 런타임 읽기경로는 모드와 무관(KB=app-schema, 등기부=registry_source). 전환 절차는
    # docs/internal-migration-mode-switch-runbook.md.
    data_mode: Literal["dev", "prod"] = "dev"

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
    jwt_access_token_expire_minutes: int = 480  # 8h — 한 근무일 (ADR-005)

    # ----- LLM / OpenAI (Phase 3에서 사용) -----
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o"
    llm_max_tokens: int = 4096
    llm_timeout_seconds: int = 60
    llm_daily_call_limit: int = 1000

    # ----- 등기부등본 API (별도 마이크로서비스, 8100 포트) -----
    registry_api_url: str = "http://localhost:8100"
    registry_internal_token: Optional[str] = None
    registry_request_timeout: int = 120

    # ----- 권리분석 source (step5) -----
    # pdf=현행 외부 8100→MinerU→LLM (안전 기본) / db=폐쇄망 NICE 6테이블 결정적 빌드 /
    # auto=rles_unq_no 있으면 db, 없으면 pdf (전환기). 6테이블 적재 전까지 pdf 유지.
    registry_source: Literal["pdf", "auto", "db"] = "pdf"

    # ----- MinerU API (PDF→markdown 사이드카, 8200 포트) -----
    mineru_api_url: str = "http://localhost:8200"
    mineru_request_timeout: int = 300

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
