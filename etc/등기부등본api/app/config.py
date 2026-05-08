from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APICK_AUTH_KEY: str
    INTERNAL_TOKEN: str
    DATABASE_URL: str

    REGISTRY_ENABLED: bool = True
    DAILY_LIMIT: int = 20
    HOURLY_LIMIT: int = 10
    DUPLICATE_BLOCK_HOURS: int = 24

    STORAGE_DIR: str = "./storage/pdf"

    APICK_BASE_URL: str = "https://apick.app"
    APICK_TIMEOUT: int = 60
    DOWNLOAD_POLL_INTERVAL: int = 5
    # 실측: 열람 응답 후 다운로드는 거의 1회로 즉시 PDF가 떨어짐.
    # 안전마진으로 8회(=최대 ~40초)면 충분.
    DOWNLOAD_POLL_MAX_TRIES: int = 8


settings = Settings()
