import re
from decimal import Decimal
from functools import lru_cache

from pydantic import field_validator
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

    @field_validator("kis_account_no")
    @classmethod
    def validate_kis_account_no(cls, v: str) -> str:
        if v and not re.match(r"^\d{8}-\d{2}$", v):
            raise ValueError(
                f"kis_account_no must match NNNNNNNN-NN format (e.g. 50192525-01), got: {v!r}"
            )
        return v

    # KIS API 호출 빈도 제한 (모의투자 EGW00201 "초당 거래건수를 초과하였습니다" 완화)
    kis_rate_limit_min_interval_seconds: float = 0.5
    kis_rate_limit_cooldown_seconds: float = 7.0

    # KIS API 요청 재시도 설정
    # 재시도 대상: httpx.ReadTimeout / ConnectError / RemoteProtocolError / EGW00201(rate limit)
    # 재시도 제외: 주문 API(place_order) — 중복주문 방지
    kis_request_max_retries: int = 2
    kis_request_retry_base_delay_seconds: float = 1.0
    kis_request_retry_max_delay_seconds: float = 5.0

    # Strategy Engine 스케줄러 (APScheduler)
    strategy_scheduler_enabled: bool = True
    strategy_scheduler_interval_seconds: int = 60

    # 주문 체결 동기화 스케줄러 (APScheduler)
    order_sync_scheduler_enabled: bool = True
    order_sync_scheduler_interval_seconds: int = 60

    # AI Analysis Provider (C-2.3)
    # 실제 API key는 C-2.4 이후 단계에서 추가한다.
    # 현재 기본값은 "fake" — 네트워크 호출 없는 테스트용 provider.
    ai_default_provider: str = "fake"
    ai_default_model: str = "fake-1.0"

    # 거래 수수료/세금 (MVP 기본값, 추후 브로커/시장 정책 변경 시 .env로 조정)
    #
    # - trading_commission_rate: 매수/매도 공통 거래 수수료율. KIS 모의투자(VTS)는
    #   실제로 수수료를 차감하지 않지만, 실전 온라인 위탁 수수료(약 0.015% 수준)를
    #   보수적으로 반영해 PnL 계산에 사용한다.
    # - trading_sell_tax_rate: 매도 시 부과되는 증권거래세(+농특세 포함) 합산율.
    #   2024년 기준 코스피 매도 거래세는 0.18% 수준으로 단계적으로 인하되는 추세이며,
    #   시장/기간에 따라 달라질 수 있으므로 정확한 값은 운영 시점에 재확인 후 조정한다.
    #
    # 두 값 모두 향후 계좌/시장별로 DB 설정(RiskConfig 등)으로 옮길 수 있도록
    # 별도 설정 항목으로 분리해 두었다.
    trading_commission_rate: Decimal = Decimal("0.00015")
    trading_sell_tax_rate: Decimal = Decimal("0.0018")


@lru_cache
def get_settings() -> Settings:
    return Settings()
