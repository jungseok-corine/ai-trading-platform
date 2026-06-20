"""C-2.55 분석 번들을 LLM 프롬프트에 결합 테스트 (fake provider)."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import StrategyVersionStatus, TradeSide
from app.domain.models.market_data import MarketData
from app.domain.models.news_context import UsMarketSnapshot
from app.domain.models.signal_log import SignalLog
from app.domain.repositories.ai_analysis import AiAnalysisRunRepository
from app.services.daily_analysis_service import DailyAnalysisService
from app.services.strategy_service import StrategyService
from app.trading.analysis.bundle_prompt import format_bundle_for_prompt

KST = ZoneInfo("Asia/Seoul")
DAY = date(2026, 6, 17)
T0 = datetime(2026, 6, 17, 10, 0, tzinfo=KST)


# --- 순수 포매터 ------------------------------------------------------------
def test_format_bundle_compact() -> None:
    bundle = {
        "macro": {"regime": "risk_off", "vix": 31.0, "vix_level": "high",
                  "us_trend": "down", "semis_strength": "weak", "session_date": "2026-06-16"},
        "trade_tape": {
            "day_summary": {"open": 100, "high": 110, "low": 99, "close": 108,
                            "vwap": 104, "range_pct": 11.1, "candle_count": 200},
            "trades": [{"side": "buy", "entry_price": 100, "status": "open",
                        "features": {"realized_return_pct": None, "entry_vs_vwap_pct": -3.8,
                                     "entry_range_percentile": 9.0, "entry_volume_zscore": -0.1,
                                     "mfe_pct": 4.1, "mae_pct": -0.1,
                                     "excursion_basis": "to_session_close"}}],
            "notable_events": [{"ts": "2026-06-17T00:49:00+00:00", "return_pct": 0.7,
                                "reasons": ["big_move", "volume_spike"]}],
        },
        "news": [], "analyst_note": "반도체 주목",
    }
    text = format_bundle_for_prompt(bundle, {"band": "sparse", "signal_count": 1,
                                             "market_active": True, "reason": "신호 적음 + 미발화"})
    assert "risk_off" in text
    assert "to_session_close" in text  # 미청산 표시
    assert "band=sparse" in text
    assert "반도체 주목" in text  # 수동 노트
    assert "구체적 파라미터 수준" in text  # 지시문


# --- DB 통합: extra_context가 저장된 프롬프트에 들어가는가 ------------------
async def test_bundle_context_reaches_stored_prompt(db_session: AsyncSession) -> None:
    svc = StrategyService(db_session)
    strategy = await svc.create_strategy("ctx")
    version = await svc.create_version(
        strategy.id,
        parameters={"strategy_type": "moving_average_cross", "symbol_code": "005930",
                    "long_window": 20},
        status=StrategyVersionStatus.TESTING,
    )
    for i in range(5):
        db_session.add(SignalLog(symbol_code="005930", signal_type=TradeSide.BUY,
                                 generated_at=T0 + timedelta(minutes=i),
                                 strategy_version_id=version.id))
    for i in range(20):
        px = Decimal("100") + Decimal(i) / 10
        db_session.add(MarketData(symbol_code="005930", timeframe="1m",
                                  ts=T0 + timedelta(minutes=i), open=px, high=px + 1,
                                  low=px - 1, close=px, volume=1000))
    db_session.add(UsMarketSnapshot(session_date=date(2026, 6, 16), vix=Decimal("31.0"),
                                    nasdaq_change_pct=Decimal("-2.0")))
    await db_session.commit()

    summary = await DailyAnalysisService(db_session).run_once(trading_day=DAY)
    assert summary.analyzed == 1
    run_id = summary.per_version[0].run_id

    run = await AiAnalysisRunRepository(db_session).get_with_responses(run_id)
    # 프롬프트에 추가 컨텍스트 블록이 결합됐는지
    assert "추가 컨텍스트" in run.prompt
    assert "risk_off" in run.prompt
    # input_payload에 감사용으로 보존됐는지
    assert "extra_context" in run.input_payload
