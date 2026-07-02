"""C-6.1: 백테스트 엔진 — market_data 히스토리컬 리플레이.

안전 검증 포함: 주문/브로커 호출 없음, Trade/Position/SignalLog 미생성.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.backtest_run import BacktestRun
from app.domain.models.market_data import MarketData
from app.domain.models.position import Position
from app.domain.models.signal_log import SignalLog
from app.domain.models.trade import Trade
from app.services.backtest_service import BacktestService

KST = timezone(timedelta(hours=9))
BASE_TS = datetime(2026, 6, 1, 9, 0, tzinfo=KST)
SYMBOL = "BT0001"


async def _seed_candles(session: AsyncSession, closes: list[int]) -> None:
    """1분 간격 캔들 시드. open은 직전 close(첫 봉은 자기 close)."""
    prev = closes[0]
    for i, c in enumerate(closes):
        session.add(
            MarketData(
                symbol_code=SYMBOL,
                timeframe="1m",
                ts=BASE_TS + timedelta(minutes=i),
                open=Decimal(prev),
                high=Decimal(max(prev, c)),
                low=Decimal(min(prev, c)),
                close=Decimal(c),
                volume=1000,
            )
        )
        prev = c
    await session.commit()


def _cross_pattern() -> list[int]:
    """골든크로스 후 데드크로스가 발생하는 가격 시퀀스 (short=3, long=5 기준)."""
    flat = [100] * 10          # 워밍업 (MA 수렴)
    up = [100 + i * 5 for i in range(1, 11)]    # 상승 → 골든크로스
    down = [150 - i * 5 for i in range(1, 11)]  # 하락 → 데드크로스
    tail = [100] * 5
    return flat + up + down + tail


@pytest.mark.asyncio
async def test_backtest_generates_trades_and_metrics(db_session: AsyncSession):
    await _seed_candles(db_session, _cross_pattern())
    service = BacktestService(db_session)

    run = await service.run(
        strategy_type="moving_average_cross",
        parameters={"short_window": 3, "long_window": 5, "quantity": 1},
        symbol_code=SYMBOL,
        timeframe="1m",
        start_ts=BASE_TS,
        end_ts=BASE_TS + timedelta(hours=1),
    )

    assert run.status == "succeeded"
    assert run.metrics is not None
    assert run.metrics["trade_count"] >= 1
    assert run.metrics["bars"] == len(_cross_pattern())
    assert run.simulated_trades
    first = run.simulated_trades[0]
    # 체결은 신호 다음 봉 시가 — entry/exit와 pnl 정합
    assert Decimal(first["pnl"]) == (
        Decimal(first["exit_price"]) * first["quantity"]
        - Decimal(first["entry_price"]) * first["quantity"]
        - Decimal(first["fees"])
    )
    assert run.metrics["win_rate"] is not None
    assert "max_drawdown_pct" in run.metrics
    assert "buy_hold_return_pct" in run.metrics


@pytest.mark.asyncio
async def test_backtest_no_side_effects_on_trading_tables(db_session: AsyncSession):
    """백테스트는 Trade/Position/SignalLog를 만들지 않는다 (안전 경계)."""
    await _seed_candles(db_session, _cross_pattern())

    async def _count(model) -> int:
        return (await db_session.execute(select(func.count()).select_from(model))).scalar_one()

    before = (await _count(Trade), await _count(Position), await _count(SignalLog))

    await BacktestService(db_session).run(
        strategy_type="moving_average_cross",
        parameters={"short_window": 3, "long_window": 5},
        symbol_code=SYMBOL,
        timeframe="1m",
        start_ts=BASE_TS,
        end_ts=BASE_TS + timedelta(hours=1),
    )

    after = (await _count(Trade), await _count(Position), await _count(SignalLog))
    assert before == after


@pytest.mark.asyncio
async def test_backtest_unknown_strategy_fails_gracefully(db_session: AsyncSession):
    run = await BacktestService(db_session).run(
        strategy_type="no_such_strategy",
        parameters={},
        symbol_code=SYMBOL,
        timeframe="1m",
        start_ts=BASE_TS,
        end_ts=BASE_TS + timedelta(hours=1),
    )
    assert run.status == "failed"
    assert "등록되지 않은" in (run.error_message or "")


@pytest.mark.asyncio
async def test_backtest_insufficient_data_fails_gracefully(db_session: AsyncSession):
    run = await BacktestService(db_session).run(
        strategy_type="moving_average_cross",
        parameters={},
        symbol_code="NODATA",
        timeframe="1m",
        start_ts=BASE_TS,
        end_ts=BASE_TS + timedelta(hours=1),
    )
    assert run.status == "failed"
    assert "캔들이 부족" in (run.error_message or "")


@pytest.mark.asyncio
async def test_backtest_forced_close_at_end(db_session: AsyncSession):
    """마지막까지 SELL이 없으면 마지막 봉 종가로 강제 청산해 지표에 반영한다."""
    # 골든크로스 후 계속 상승 (데드크로스 없음)
    closes = [100] * 10 + [100 + i * 3 for i in range(1, 21)]
    await _seed_candles(db_session, closes)

    run = await BacktestService(db_session).run(
        strategy_type="moving_average_cross",
        parameters={"short_window": 3, "long_window": 5},
        symbol_code=SYMBOL,
        timeframe="1m",
        start_ts=BASE_TS,
        end_ts=BASE_TS + timedelta(hours=1),
    )
    assert run.status == "succeeded"
    assert run.simulated_trades
    assert run.simulated_trades[-1]["forced_close"] is True
    # 상승장 롱 포지션 → 수익
    assert Decimal(run.simulated_trades[-1]["pnl"]) > 0


@pytest.mark.asyncio
async def test_backtest_persisted_and_listable(db_session: AsyncSession):
    await _seed_candles(db_session, _cross_pattern())
    service = BacktestService(db_session)
    run = await service.run(
        strategy_type="moving_average_cross",
        parameters={"short_window": 3, "long_window": 5},
        symbol_code=SYMBOL,
        timeframe="1m",
        start_ts=BASE_TS,
        end_ts=BASE_TS + timedelta(hours=1),
    )
    fetched = await service.get(run.id)
    assert fetched is not None and fetched.id == run.id
    recent = await service.list_recent(limit=5)
    assert any(r.id == run.id for r in recent)
    assert isinstance(fetched, BacktestRun)
