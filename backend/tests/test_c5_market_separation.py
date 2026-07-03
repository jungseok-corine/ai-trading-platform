"""C-5.11: 시장별 구조 분리 — signal_logs.market + 일일리포트 시장별 집계."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.domain.models.account import Account
from app.domain.models.enums import (
    AccountType,
    MarketCode,
    OrderStatus,
    StrategyVersionStatus,
    TradeSide,
)
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.trade import Trade
from app.services.daily_report_service import DailyReportService
from app.services.market_data_service import MarketDataService
from app.services.signal_service import SignalService
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.rsi_reversion import RsiReversionStrategy

from tests.test_strategy_runner_service import FakeBrokerClient


def _now() -> datetime:
    return datetime.now(KST)


async def test_daily_report_separates_signals_by_market(db_session: AsyncSession) -> None:
    now = _now()
    db_session.add_all([
        SignalLog(symbol_code="005930", market="KR", signal_type=TradeSide.BUY, generated_at=now),
        SignalLog(symbol_code="AAPL", market="US", signal_type=TradeSide.SELL, generated_at=now),
        SignalLog(symbol_code="TSLA", market="US", signal_type=TradeSide.BUY, generated_at=now),
    ])
    await db_session.commit()

    svc = DailyReportService(db_session)
    kr = await svc.generate(market=MarketCode.KR)
    us = await svc.generate(market=MarketCode.US)

    assert kr.sections["signal_activity"]["total"] == 1
    assert us.sections["signal_activity"]["total"] == 2
    assert us.sections["signal_activity"]["buy"] == 1
    assert us.sections["signal_activity"]["sell"] == 1


async def test_daily_report_separates_trades_by_market(db_session: AsyncSession) -> None:
    acc = Account(account_type=AccountType.PAPER, broker_account_no="50000000-01")
    db_session.add(acc)
    await db_session.flush()
    db_session.add_all([
        Trade(account_id=acc.id, symbol_code="005930", market="KR", side=TradeSide.BUY,
              quantity=1, pnl_amount=Decimal("1000"), order_status=OrderStatus.FILLED),
        Trade(account_id=acc.id, symbol_code="AAPL", market="US", side=TradeSide.SELL,
              quantity=1, pnl_amount=Decimal("5.50"), order_status=OrderStatus.FILLED),
    ])
    await db_session.commit()

    svc = DailyReportService(db_session)
    kr = await svc.generate(market=MarketCode.KR)
    us = await svc.generate(market=MarketCode.US)

    assert kr.sections["trade_summary"]["trades"] == 1
    assert Decimal(kr.sections["trade_summary"]["realized_pnl"]) == Decimal("1000")
    assert us.sections["trade_summary"]["trades"] == 1
    assert Decimal(us.sections["trade_summary"]["realized_pnl"]) == Decimal("5.50")


async def test_signal_log_records_market_us(db_session: AsyncSession) -> None:
    """generate_and_log_signal에 market=US를 주면 signal_logs.market='US'로 기록된다."""
    strategy = Strategy(name="us market sig", description="t")
    db_session.add(strategy)
    await db_session.flush()
    version = StrategyVersion(
        strategy_id=strategy.id, version_no=1,
        parameters={"strategy_type": "rsi_reversion", "rsi_period": 14},
        status=StrategyVersionStatus.ACTIVE,
    )
    db_session.add(version)
    await db_session.flush()

    # 단조 상승 캔들 → RSI=100 → 매도. candle_cache로 브로커 호출 회피(US는 overseas 필요).
    rising = [
        MinuteCandle(
            business_date="20260622", trade_time=f"22{30 + i:02d}00",
            open_price=Decimal(100 + i), high_price=Decimal(100 + i),
            low_price=Decimal(100 + i), close_price=Decimal(100 + i), volume=1000,
        )
        for i in range(16)
    ]
    svc = SignalService(db_session, MarketDataService(FakeBrokerClient({})))
    log = await svc.generate_and_log_signal(
        RsiReversionStrategy.from_params({"rsi_period": 14}), "AAPL", version.id,
        strategy_params={"timeframe": "1m"}, candle_cache={("AAPL", "1m"): rising},
        market="US", exchange="NAS",
    )

    assert log is not None
    assert log.market == "US"
    assert log.signal_type == TradeSide.SELL
