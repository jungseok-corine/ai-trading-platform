from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Trading Platform"
    app_env: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://trading:trading@localhost:5432/trading_platform"

    # KIS Open API
    kis_app_key: str = ""
    kis_app_secret: str = ""
    kis_account_no: str = ""  # 계좌번호 전체, 예: "12345678-01"
    kis_paper_base_url: str = "https://openapivts.koreainvestment.com:29443"
    kis_real_base_url: str = "https://openapi.koreainvestment.com:9443"
    kis_token_cache_path: str = ".cache/kis_token.json"

    # Strategy Engine 스케줄러 (APScheduler)
    strategy_scheduler_enabled: bool = True
    strategy_scheduler_interval_seconds: int = 60

    # 주문 체결 동기화 스케줄러 (APScheduler)
    order_sync_scheduler_enabled: bool = True
    order_sync_scheduler_interval_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
