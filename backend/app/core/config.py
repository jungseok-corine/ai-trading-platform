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
    # SQLAlchemy SQL echo. 기본 off — 모든 쿼리를 콘솔에 출력하면 로그가 매우 시끄럽다.
    # 쿼리 디버깅이 필요할 때만 DB_ECHO=true로 켠다.
    db_echo: bool = False

    database_url: str = "postgresql+asyncpg://trading:trading@localhost:5432/trading_platform"

    # KIS Open API — 모의투자 (paper)
    kis_app_key: str = ""
    kis_app_secret: str = ""
    kis_account_no: str = ""  # 계좌번호 전체, 예: "12345678-01"
    kis_paper_base_url: str = "https://openapivts.koreainvestment.com:29443"
    kis_real_base_url: str = "https://openapi.koreainvestment.com:9443"
    kis_token_cache_path: str = ".cache/kis_token.json"

    # KIS Open API — 실전투자 (real, C-2.13)
    # 실전 계좌는 모의 계좌와 별도 app_key/app_secret/account_no를 사용한다.
    # 미설정이면 실전 브로커가 초기화되지 않는다.
    kis_real_app_key: str = ""
    kis_real_app_secret: str = ""
    kis_real_account_no: str = ""  # 계좌번호 전체, 예: "12345678-01"
    kis_real_token_cache_path: str = ".cache/kis_real_token.json"

    # C-2.13: 실전 주문 활성화 플래그 — 기본값은 반드시 False (read-only 모드).
    # True로 변경하는 것은 사람이 명시적으로 해야 한다.
    # AI 분석 결과, 자동화 코드, 스케줄러는 이 값을 변경해서는 안 된다.
    kis_real_trading_enabled: bool = False

    @field_validator("kis_account_no")
    @classmethod
    def validate_kis_account_no(cls, v: str) -> str:
        if v and not re.match(r"^\d{8}-\d{2}$", v):
            raise ValueError(
                f"kis_account_no must match NNNNNNNN-NN format (e.g. 50192525-01), got: {v!r}"
            )
        return v

    @field_validator("kis_real_account_no")
    @classmethod
    def validate_kis_real_account_no(cls, v: str) -> str:
        if v and not re.match(r"^\d{8}-\d{2}$", v):
            raise ValueError(
                f"kis_real_account_no must match NNNNNNNN-NN format (e.g. 50192525-01), got: {v!r}"
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
    # 신호 생성 시 최신 캔들 신선도(분) 가드 — 장 마감/휴장으로 시세가 멈춰 캔들이
    # 이 값보다 오래되면 신호를 생성하지 않는다(스테일 데이터로 인한 허위 신호 방지).
    # 0 이하로 두면 가드를 비활성화한다.
    signal_max_candle_staleness_minutes: int = 15
    # 시장 세션 게이팅 — 종목의 시장(KR/US)이 정규/종가동시호가 단계가 아니면 신호 생성을
    # 건너뛴다(장외 시간 KIS 호출/허위 신호 절감). 휴장일은 신선도 가드가 백스톱.
    strategy_session_gating_enabled: bool = True

    # 주문 체결 동기화 스케줄러 (APScheduler)
    order_sync_scheduler_enabled: bool = True
    order_sync_scheduler_interval_seconds: int = 60

    # 통합 trading state sync 스케줄러 (order sync + position reconciliation)
    # order_sync_job과 중복 KIS 호출을 막기 위해 기본값은 False.
    # order_sync_job을 비활성화하고 이 job만 활성화하거나, 독립 주기로 운영한다.
    trading_state_sync_scheduler_enabled: bool = False
    trading_state_sync_scheduler_interval_seconds: int = 180

    # 일일 AI 리서치 리포트 (C-2.29). 기본 비활성 — 명시적으로 켤 때만 매일 장마감 후 생성.
    daily_report_scheduler_enabled: bool = False
    daily_report_scheduler_hour: int = 15
    daily_report_scheduler_minute: int = 45

    # 수급 데이터 자동 수집 (C-2.34). 기본 비활성 — KIS 자격증명이 있을 때만 켠다.
    data_refresh_scheduler_enabled: bool = False
    data_refresh_scheduler_hour: int = 16
    data_refresh_scheduler_minute: int = 0
    data_refresh_lookback_days: int = 5

    # 자율 연구 파이프라인 (C-2.35). 기본 비활성 — 스캔→후보→배정을 주기적으로 자동 실행.
    research_pipeline_scheduler_enabled: bool = False
    research_pipeline_interval_seconds: int = 300

    # 스캐너 룰 자동 점검 (C-2.40). 기본 비활성 — 후보 성과 분석→조건 강화 제안(pending).
    # data_refresh(16:00) 이후에 돌려 성과 데이터가 갱신된 상태로 점검한다.
    scanner_review_scheduler_enabled: bool = False
    scanner_review_scheduler_hour: int = 16
    scanner_review_scheduler_minute: int = 10
    scanner_review_horizon_minutes: int = 30

    # 전략 버전 자동 점검 (C-2.42). 기본 비활성 — 거래 성과 분석→파라미터 조정 제안(pending).
    # 장마감/일일 리포트 이후 16:20에 돌린다.
    strategy_review_scheduler_enabled: bool = False
    strategy_review_scheduler_hour: int = 16
    strategy_review_scheduler_minute: int = 20

    # 미국장 스냅샷 수집 (C-2.44). 기본 provider는 "manual"(외부 호출 없음, 수동 입력 보존).
    # 벤더 어댑터(alphavantage/finnhub/twelvedata)는 API 키가 준비되면 붙인다.
    # 미국장 스냅샷 수집 (C-2.44/C-2.48). provider는 "manual"(외부 호출 없음, 기본),
    # "fred", "twelvedata", "fred_twelvedata"(권장: FRED 매크로 + TD가 SOX 보강).
    us_market_provider: str = "manual"
    # FRED(미 연준 세인트루이스) — VIX/10년물 금리/S&P500/나스닥종합. 무료.
    fred_api_key: str | None = None
    # Twelve Data — SOX(기본 SOXX ETF proxy) 등 보강. 무료 800콜/일.
    twelvedata_api_key: str | None = None
    # SOX 대용 심볼(SOX 지수는 라이선스 제약이 많아 ETF proxy를 기본으로 둔다).
    us_market_sox_symbol: str = "SOXX"
    us_market_provider_timeout_seconds: float = 10.0
    us_market_refresh_scheduler_enabled: bool = False
    us_market_refresh_scheduler_hour: int = 7  # KST 아침(미국장 마감 후)
    us_market_refresh_scheduler_minute: int = 0

    # 일일 AI 분석 잡 (C-2.54). 기본 비활성 + 기본 provider는 fake(실수로 유료 호출 방지).
    # A/B 기간엔 mode=dual로 Claude+GPT 둘 다 매일 분석해 비교한 뒤 single로 확정한다.
    ai_daily_analysis_enabled: bool = False
    ai_daily_analysis_scheduler_hour: int = 15  # KR 장마감(15:30) 직후
    ai_daily_analysis_scheduler_minute: int = 40
    ai_analysis_mode: str = "single"  # single | dual
    ai_analysis_prompt_type: str = "improvement"  # overview | risk | improvement
    ai_analysis_provider: str = "fake"
    ai_analysis_model: str | None = None  # None이면 provider 기본 모델
    ai_analysis_secondary_provider: str = "fake"
    ai_analysis_secondary_model: str | None = None
    # 활동량 게이트 임계값 (C-2.54).
    ai_analysis_few_threshold: int = 3
    ai_analysis_many_threshold: int = 15
    ai_analysis_active_range_pct: float = 2.0
    ai_analysis_active_notable: int = 3
    # LLM 출력→제안 연결 (C-2.56). 가설 confidence가 이 값 이상일 때만 pending 제안 생성.
    ai_analysis_min_confidence: float = 0.5

    # 운영 알림 채널 (C-3.8/C-3.15). 기본 none(외부 전송 없음). "log"는 로거에만 남긴다.
    # "telegram"은 아래 토큰/chat_id가 모두 있을 때만 전송(없으면 no-op). 사용자가 명시적으로 켠다.
    notification_provider: str = "none"
    notification_timeout_seconds: float = 10.0
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    # 운영 다이제스트 잡 (C-3.9). 기본 비활성 — 켜면 매일 다이제스트를 설정 채널로 보낸다.
    # 채널 기본 none이라 켜도 외부 전송은 없다(채널을 함께 설정해야 실제 발송).
    operations_digest_scheduler_enabled: bool = False
    operations_digest_scheduler_hour: int = 16
    operations_digest_scheduler_minute: int = 30
    operations_digest_window_days: int = 30

    # AI 비용 예산 가드 (C-3.7). 0이면 예산 미설정(가드 비활성). 윈도(기본 30일) 추정비용과
    # 비교해 ok/warn/over를 매긴다. 단가는 추정치이므로 경보는 가늠자 — 사람이 최종 판단.
    ai_cost_monthly_budget_usd: float = 0.0
    ai_cost_alert_threshold_pct: float = 80.0

    # 뉴스 큐레이터 LLM 정밀화 (C-2.65). 기본 비활성(룰 기반만). 켜면 싼 모델로 보강.
    news_curator_llm_enabled: bool = False
    news_curator_provider: str = "fake"
    news_curator_model: str | None = None

    # DART 공시 수집 (C-2.59). 무료 키. 기본 비활성 — 보유/관심 종목 중요 공시만 저장.
    dart_api_key: str | None = None
    dart_provider_timeout_seconds: float = 10.0
    dart_min_materiality: float = 0.5
    dart_ingest_scheduler_enabled: bool = False
    dart_ingest_interval_seconds: int = 600  # 장중 10분 폴링

    # AI Analysis Provider (C-2.3)
    # 현재 기본값은 "fake" — 네트워크 호출 없는 테스트용 provider.
    ai_default_provider: str = "fake"
    ai_default_model: str = "fake-1.0"

    # OpenAI provider (C-2.7.1/C-2.7.5)
    # AI_OPENAI_API_KEY를 .env에 설정하면 openai provider가 활성화된다.
    # key가 없으면 analyze() 호출 시 AnalysisProviderError가 발생한다.
    ai_openai_api_key: str | None = None
    ai_openai_model: str = "gpt-4o"
    ai_openai_timeout_seconds: int = 60
    # 출력 토큰 상한 (비용 통제용). 긴 분석이 필요하면 환경변수로 늘린다.
    ai_openai_max_output_tokens: int = 1024

    # Anthropic provider (C-2.7.2/C-2.7.5)
    # AI_ANTHROPIC_API_KEY를 .env에 설정하면 anthropic provider가 활성화된다.
    # key가 없으면 analyze() 호출 시 AnalysisProviderError가 발생한다.
    ai_anthropic_api_key: str | None = None
    ai_anthropic_model: str = "claude-sonnet-4-6"
    # 출력 토큰 상한 (비용 통제용). 긴 분석이 필요하면 환경변수로 늘린다.
    ai_anthropic_max_tokens: int = 4096
    ai_anthropic_timeout_seconds: int = 120

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
