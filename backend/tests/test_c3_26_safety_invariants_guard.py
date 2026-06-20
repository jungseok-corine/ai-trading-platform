"""C-3.26 안전 불변식 회귀 가드.

CLAUDE.md의 '🔒 안전 불변식'을 코드로 못박는다. 누군가(사람이든 AI든) 안전 기본값을
슬그머니 바꾸면 이 테스트가 실패해 알린다. .env의 로컬 오버라이드와 무관하게 **코드 기본값**을
검증하기 위해 `_env_file=None`으로 새 Settings를 만든다.

핵심 불변식:
- 실거래 비활성(KIS_REAL_TRADING_ENABLED=false)
- AI provider 기본 fake(실수 유료호출 방지) + 알림 채널 기본 none(외부 전송 없음)
- 연구/분석/공시/다이제스트 등 '새 잡'은 기본 비활성
- 비용 예산 가드 기본 미설정(0)
"""
from app.core.config import Settings


def _fresh() -> Settings:
    # 로컬 .env 오버라이드를 무시하고 코드 기본값만 본다.
    return Settings(_env_file=None)


def test_real_trading_is_disabled_by_default() -> None:
    assert _fresh().kis_real_trading_enabled is False


def test_ai_and_notification_providers_are_safe_defaults() -> None:
    s = _fresh()
    # 유료 호출 방지: 분석/큐레이터/기본 provider 모두 fake
    assert s.ai_analysis_provider == "fake"
    assert s.ai_analysis_secondary_provider == "fake"
    assert s.ai_default_provider == "fake"
    assert s.news_curator_provider == "fake"
    assert s.news_curator_llm_enabled is False
    # 외부 전송 방지: 알림 채널 none, 미국장 provider manual
    assert s.notification_provider == "none"
    assert s.us_market_provider == "manual"
    # 비용 예산 가드 미설정(0)
    assert float(s.ai_cost_monthly_budget_usd) == 0.0


def test_research_and_new_jobs_default_disabled() -> None:
    """연구 루프·분석·수집·다이제스트 등 '새 잡'은 기본 비활성이어야 한다.

    (예외: strategy_runner/order_sync는 기존부터 활성 — 별도 명시.)
    """
    s = _fresh()
    must_be_off = [
        "trading_state_sync_scheduler_enabled",
        "daily_report_scheduler_enabled",
        "data_refresh_scheduler_enabled",
        "research_pipeline_scheduler_enabled",
        "scanner_review_scheduler_enabled",
        "strategy_review_scheduler_enabled",
        "us_market_refresh_scheduler_enabled",
        "ai_daily_analysis_enabled",
        "dart_ingest_scheduler_enabled",
        "operations_digest_scheduler_enabled",
    ]
    off = {name: getattr(s, name) for name in must_be_off}
    assert all(v is False for v in off.values()), f"기본 활성이면 안 되는 잡: {off}"


def test_historically_on_jobs_unchanged() -> None:
    # 이 둘은 의도적으로 기본 활성(모의투자 운영용). 바뀌면 의식적 결정이어야 한다.
    s = _fresh()
    assert s.strategy_scheduler_enabled is True
    assert s.order_sync_scheduler_enabled is True
