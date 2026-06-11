from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, SchedulerRunStatus, StrategyVersionStatus, TradeSide
from app.domain.models.scheduler_run import SchedulerRun
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.trade import Trade
from app.scheduler.jobs import ORDER_SYNC_JOB_ID, STRATEGY_RUNNER_JOB_ID, order_sync_job, run_strategy_job
from app.trading.broker.base import BrokerClient
from app.trading.broker.schemas import (
    AccountBalance,
    AccountSummary,
    MinuteCandle,
    OrderExecution,
    OrderRequest,
    OrderResult,
    PriceQuote,
)

KST = ZoneInfo("Asia/Seoul")

GOLDEN_CROSS_CLOSES = [100] * 20 + [200]

GOLDEN_CROSS_PARAMS = {
    "strategy_type": "moving_average_cross",
    "symbol_code": "005930",
    "short_window": 5,
    "long_window": 20,
    "quantity": 1,
    "timeframe": "1m",
    "enabled": True,
    "auto_trade_enabled": False,
}


@pytest_asyncio.fixture
async def job_session_factory(monkeypatch):
    """run_strategy_job/order_sync_job이 사용하는 async_session_factory를 테스트 전용 엔진으로 대체한다.

    app.db.session의 전역 엔진을 그대로 쓰면 pytest-asyncio가 테스트마다 새 이벤트 루프를
    만들 때 이전 루프에 묶인 asyncpg 커넥션을 재사용하게 되어 오류가 발생한다.
    """
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("app.scheduler.jobs.async_session_factory", factory)
    yield factory
    await engine.dispose()


def _make_candles(closes: list[int]) -> list[MinuteCandle]:
    candles = []
    for i, close in enumerate(closes):
        price = Decimal(close)
        candles.append(
            MinuteCandle(
                business_date="20260610",
                trade_time=f"{900 + i:04d}00",
                open_price=price,
                high_price=price,
                low_price=price,
                close_price=price,
                volume=1000,
            )
        )
    return candles


class FakeBrokerClient(BrokerClient):
    """scheduler job 테스트용: 분봉/체결 데이터를 고정값 또는 오류로 반환한다."""

    def __init__(
        self,
        candles_by_symbol: dict[str, list[MinuteCandle]] | None = None,
        executions: list[OrderExecution] | None = None,
        get_daily_executions_error: Exception | None = None,
    ) -> None:
        self._candles_by_symbol = candles_by_symbol or {}
        self._executions = executions or []
        self._get_daily_executions_error = get_daily_executions_error

    async def get_current_price(self, symbol_code: str) -> PriceQuote:
        raise NotImplementedError

    async def get_minute_candles(
        self, symbol_code: str, target_time: str | None = None, include_past_data: bool = True
    ) -> list[MinuteCandle]:
        return self._candles_by_symbol.get(symbol_code, [])

    async def get_account_balance(self) -> AccountBalance:
        return AccountBalance(
            holdings=[],
            summary=AccountSummary(
                total_deposit=Decimal("0"),
                total_purchase_amount=Decimal("0"),
                total_evaluation_amount=Decimal("0"),
                total_profit_loss_amount=Decimal("0"),
            ),
        )

    async def place_order(self, order: OrderRequest) -> OrderResult:
        raise NotImplementedError

    async def get_daily_executions(self, target_date: str | None = None) -> list[OrderExecution]:
        if self._get_daily_executions_error is not None:
            raise self._get_daily_executions_error
        return self._executions


async def test_run_strategy_job_records_success(job_session_factory) -> None:
    async with job_session_factory() as session:
        strategy = Strategy(name="Scheduler Job Test MA", description="test")
        session.add(strategy)
        await session.flush()
        version = StrategyVersion(
            strategy_id=strategy.id,
            version_no=1,
            parameters=GOLDEN_CROSS_PARAMS,
            status=StrategyVersionStatus.ACTIVE,
        )
        session.add(version)
        await session.commit()
        strategy_id = strategy.id
        version_id = version.id

    app = FastAPI()
    app.state.broker_client = FakeBrokerClient(candles_by_symbol={"005930": _make_candles(GOLDEN_CROSS_CLOSES)})

    try:
        await run_strategy_job(app)

        assert app.state.scheduler_last_error is None
        assert app.state.scheduler_last_run_at is not None

        async with job_session_factory() as session:
            runs = (
                (
                    await session.execute(
                        select(SchedulerRun)
                        .where(SchedulerRun.job_id == STRATEGY_RUNNER_JOB_ID)
                        .order_by(SchedulerRun.id.desc())
                        .limit(1)
                    )
                )
                .scalars()
                .all()
            )
        assert len(runs) == 1
        run = runs[0]
        assert run.status == SchedulerRunStatus.SUCCESS
        assert run.error_message is None
        assert run.summary is not None
        assert run.summary["versions_run"] == 1
        assert run.summary["signals_created"] == 1
    finally:
        async with job_session_factory() as session:
            await session.execute(delete(SchedulerRun).where(SchedulerRun.job_id == STRATEGY_RUNNER_JOB_ID))
            await session.execute(delete(SignalLog).where(SignalLog.strategy_version_id == version_id))
            await session.execute(delete(Strategy).where(Strategy.id == strategy_id))
            await session.commit()


async def test_run_strategy_job_records_failure_when_broker_missing(job_session_factory) -> None:
    app = FastAPI()  # app.state.broker_client 미설정 -> AttributeError 발생을 유도

    try:
        await run_strategy_job(app)  # 예외가 밖으로 전파되면 안 된다

        assert app.state.scheduler_last_error is not None
        assert app.state.scheduler_last_run_at is not None

        async with job_session_factory() as session:
            runs = (
                (
                    await session.execute(
                        select(SchedulerRun)
                        .where(SchedulerRun.job_id == STRATEGY_RUNNER_JOB_ID)
                        .order_by(SchedulerRun.id.desc())
                        .limit(1)
                    )
                )
                .scalars()
                .all()
            )
        assert len(runs) == 1
        run = runs[0]
        assert run.status == SchedulerRunStatus.FAILED
        assert run.error_message is not None
        assert run.summary is not None
        assert run.summary["errors"]
    finally:
        async with job_session_factory() as session:
            await session.execute(delete(SchedulerRun).where(SchedulerRun.job_id == STRATEGY_RUNNER_JOB_ID))
            await session.commit()


async def test_order_sync_job_records_success_with_no_errors(job_session_factory) -> None:
    app = FastAPI()
    app.state.broker_client = FakeBrokerClient()

    try:
        await order_sync_job(app)

        assert app.state.order_sync_last_error is None
        assert app.state.order_sync_last_run_at is not None

        async with job_session_factory() as session:
            runs = (
                (
                    await session.execute(
                        select(SchedulerRun)
                        .where(SchedulerRun.job_id == ORDER_SYNC_JOB_ID)
                        .order_by(SchedulerRun.id.desc())
                        .limit(1)
                    )
                )
                .scalars()
                .all()
            )
        assert len(runs) == 1
        run = runs[0]
        assert run.status == SchedulerRunStatus.SUCCESS
        assert run.error_message is None
    finally:
        async with job_session_factory() as session:
            await session.execute(delete(SchedulerRun).where(SchedulerRun.job_id == ORDER_SYNC_JOB_ID))
            await session.commit()


async def test_order_sync_job_records_failure_when_get_daily_executions_raises(job_session_factory) -> None:
    async with job_session_factory() as session:
        account = Account(account_type=AccountType.PAPER, broker_account_no="00000000-99")
        session.add(account)
        await session.flush()
        trade = Trade(
            account_id=account.id,
            symbol_code="005930",
            side=TradeSide.BUY,
            quantity=1,
            order_status=OrderStatus.PENDING,
            broker_order_id="0000000099",
        )
        session.add(trade)
        await session.commit()
        account_id = account.id
        trade_id = trade.id

    app = FastAPI()
    app.state.broker_client = FakeBrokerClient(get_daily_executions_error=RuntimeError("조회 실패"))

    try:
        await order_sync_job(app)

        assert app.state.order_sync_last_error is not None
        assert app.state.order_sync_last_run_at is not None

        async with job_session_factory() as session:
            runs = (
                (
                    await session.execute(
                        select(SchedulerRun)
                        .where(SchedulerRun.job_id == ORDER_SYNC_JOB_ID)
                        .order_by(SchedulerRun.id.desc())
                        .limit(1)
                    )
                )
                .scalars()
                .all()
            )
        assert len(runs) == 1
        run = runs[0]
        assert run.status == SchedulerRunStatus.FAILED
        assert run.error_message is not None
        assert run.summary is not None
        assert run.summary["errors"]
    finally:
        async with job_session_factory() as session:
            await session.execute(delete(SchedulerRun).where(SchedulerRun.job_id == ORDER_SYNC_JOB_ID))
            await session.execute(delete(Trade).where(Trade.id == trade_id))
            await session.execute(delete(Account).where(Account.id == account_id))
            await session.commit()
