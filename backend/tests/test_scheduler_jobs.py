from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, SchedulerRunStatus, StrategyVersionStatus, TradeSide
from app.domain.models.market_data import MarketData
from app.domain.models.scheduler_run import SchedulerRun
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.trade import Trade
from app.scheduler.jobs import (
    ORDER_SYNC_JOB_ID,
    STRATEGY_RUNNER_JOB_ID,
    US_MARKET_REFRESH_JOB_ID,
    order_sync_job,
    run_strategy_job,
    run_us_market_refresh_job,
)
from app.trading.broker.base import BrokerClient
from app.trading.broker.schemas import (
    AccountBalance,
    AccountHolding,
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
        candles_error_by_symbol: dict[str, Exception] | None = None,
    ) -> None:
        self._candles_by_symbol = candles_by_symbol or {}
        self._executions = executions or []
        self._get_daily_executions_error = get_daily_executions_error
        self._candles_error_by_symbol = candles_error_by_symbol or {}

    async def get_current_price(self, symbol_code: str) -> PriceQuote:
        raise NotImplementedError

    async def get_minute_candles(
        self, symbol_code: str, target_time: str | None = None, include_past_data: bool = True
    ) -> list[MinuteCandle]:
        if symbol_code in self._candles_error_by_symbol:
            raise self._candles_error_by_symbol[symbol_code]
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

    async def get_account_positions(self) -> list[AccountHolding]:
        return []

    async def place_order(self, order: OrderRequest) -> OrderResult:
        raise NotImplementedError

    async def get_daily_executions(self, start_date: str | None = None, end_date: str | None = None) -> list[OrderExecution]:
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
            await session.execute(delete(MarketData))
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
        assert run.status == SchedulerRunStatus.SKIPPED
        assert run.error_message is None
        assert run.summary["skipped_reason"] == "no_pending_orders"
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


async def test_run_strategy_job_partial_failure_is_success(job_session_factory) -> None:
    """일부 version이 httpx 오류로 실패해도 일부가 성공하면 job status는 SUCCESS다."""
    async with job_session_factory() as session:
        strategy_ok = Strategy(name="Scheduler Partial OK", description="test")
        strategy_fail = Strategy(name="Scheduler Partial Fail", description="test")
        session.add(strategy_ok)
        session.add(strategy_fail)
        await session.flush()
        version_ok = StrategyVersion(
            strategy_id=strategy_ok.id,
            version_no=1,
            parameters={**GOLDEN_CROSS_PARAMS, "symbol_code": "005930"},
            status=StrategyVersionStatus.ACTIVE,
        )
        version_fail = StrategyVersion(
            strategy_id=strategy_fail.id,
            version_no=1,
            parameters={**GOLDEN_CROSS_PARAMS, "symbol_code": "999999"},
            status=StrategyVersionStatus.ACTIVE,
        )
        session.add(version_ok)
        session.add(version_fail)
        await session.commit()
        ok_strategy_id = strategy_ok.id
        fail_strategy_id = strategy_fail.id
        ok_version_id = version_ok.id
        fail_version_id = version_fail.id

    app = FastAPI()
    app.state.broker_client = FakeBrokerClient(
        candles_by_symbol={"005930": _make_candles(GOLDEN_CROSS_CLOSES)},
        candles_error_by_symbol={"999999": httpx.ReadTimeout("timeout")},
    )

    try:
        await run_strategy_job(app)

        assert app.state.scheduler_last_error is None  # 일부 성공이므로 error=None
        assert app.state.scheduler_last_run_at is not None

        async with job_session_factory() as session:
            run = (
                (
                    await session.execute(
                        select(SchedulerRun)
                        .where(SchedulerRun.job_id == STRATEGY_RUNNER_JOB_ID)
                        .order_by(SchedulerRun.id.desc())
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
        assert run is not None
        assert run.status == SchedulerRunStatus.SUCCESS
        assert run.error_message is None
        assert run.summary["versions_run"] == 2
        assert run.summary["versions_succeeded"] == 1
        assert run.summary["versions_failed"] == 1
        assert "999999" in run.summary["failed_symbols"]
    finally:
        async with job_session_factory() as session:
            await session.execute(delete(SchedulerRun).where(SchedulerRun.job_id == STRATEGY_RUNNER_JOB_ID))
            await session.execute(delete(SignalLog).where(SignalLog.strategy_version_id.in_([ok_version_id, fail_version_id])))
            await session.execute(delete(MarketData))
            await session.execute(delete(StrategyVersion).where(StrategyVersion.id.in_([ok_version_id, fail_version_id])))
            await session.execute(delete(Strategy).where(Strategy.id.in_([ok_strategy_id, fail_strategy_id])))
            await session.commit()


async def test_run_strategy_job_all_versions_fail_records_failed(job_session_factory) -> None:
    """모든 version이 실패하면 job status는 FAILED다."""
    async with job_session_factory() as session:
        strategy = Strategy(name="Scheduler All Fail", description="test")
        session.add(strategy)
        await session.flush()
        version = StrategyVersion(
            strategy_id=strategy.id,
            version_no=1,
            parameters={**GOLDEN_CROSS_PARAMS, "symbol_code": "999999"},
            status=StrategyVersionStatus.ACTIVE,
        )
        session.add(version)
        await session.commit()
        strategy_id = strategy.id
        version_id = version.id

    app = FastAPI()
    app.state.broker_client = FakeBrokerClient(
        candles_error_by_symbol={"999999": httpx.ReadTimeout("timeout")},
    )

    try:
        await run_strategy_job(app)

        assert app.state.scheduler_last_error is not None
        assert app.state.scheduler_last_run_at is not None

        async with job_session_factory() as session:
            run = (
                (
                    await session.execute(
                        select(SchedulerRun)
                        .where(SchedulerRun.job_id == STRATEGY_RUNNER_JOB_ID)
                        .order_by(SchedulerRun.id.desc())
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
        assert run is not None
        assert run.status == SchedulerRunStatus.FAILED
        assert run.error_message is not None
        assert run.summary["versions_failed"] == 1
        assert run.summary["versions_succeeded"] == 0
    finally:
        async with job_session_factory() as session:
            await session.execute(delete(SchedulerRun).where(SchedulerRun.job_id == STRATEGY_RUNNER_JOB_ID))
            await session.execute(delete(StrategyVersion).where(StrategyVersion.id == version_id))
            await session.execute(delete(Strategy).where(Strategy.id == strategy_id))
            await session.commit()


async def test_run_strategy_job_rate_limit_only_not_failed(job_session_factory) -> None:
    """레이트리밋(EGW00201)만으로 전부 실패하면 run은 FAILED가 아니라 SUCCESS다(노이즈 억제)."""
    from app.trading.broker.exceptions import KISAPIError

    async with job_session_factory() as session:
        strategy = Strategy(name="Scheduler RateLimit", description="test")
        session.add(strategy)
        await session.flush()
        version = StrategyVersion(
            strategy_id=strategy.id, version_no=1,
            parameters={**GOLDEN_CROSS_PARAMS, "symbol_code": "999998"},
            status=StrategyVersionStatus.ACTIVE,
        )
        session.add(version)
        await session.commit()
        strategy_id, version_id = strategy.id, version.id

    app = FastAPI()
    app.state.broker_client = FakeBrokerClient(
        candles_error_by_symbol={"999998": KISAPIError("EGW00201", "초당 거래건수를 초과하였습니다.")},
    )

    try:
        await run_strategy_job(app)
        async with job_session_factory() as session:
            run = (
                await session.execute(
                    select(SchedulerRun)
                    .where(SchedulerRun.job_id == STRATEGY_RUNNER_JOB_ID)
                    .order_by(SchedulerRun.id.desc())
                    .limit(1)
                )
            ).scalars().first()
        assert run is not None
        # 전부 실패했지만 레이트리밋(일시적)이라 FAILED가 아니다.
        assert run.status == SchedulerRunStatus.SUCCESS
        assert run.summary["versions_failed"] == 1  # 오류 자체는 요약에 기록
    finally:
        async with job_session_factory() as session:
            await session.execute(delete(SchedulerRun).where(SchedulerRun.job_id == STRATEGY_RUNNER_JOB_ID))
            await session.execute(delete(StrategyVersion).where(StrategyVersion.id == version_id))
            await session.execute(delete(Strategy).where(Strategy.id == strategy_id))
            await session.commit()


# ---------------------------------------------------------------------------
# us_market_refresh: scheduler_runs 기록 (스케줄러 건강 점검 정확도)
# ---------------------------------------------------------------------------
async def test_us_market_refresh_job_records_success(job_session_factory, monkeypatch) -> None:
    """run_us_market_refresh_job이 성공 시 us_market_refresh scheduler_run을 기록한다.

    기록 전에는 SchedulerHealthService가 '활성이나 실행 기록 없음'으로 잘못 표시했다.
    refresh는 mock — 외부 US market API를 호출하지 않는다.
    """
    from app.services.us_market_refresh_service import RefreshResult, UsMarketRefreshService

    async def _fake_refresh(self):
        return RefreshResult(provider="manual", updated=False, session_date=None,
                             reason="provider returned no data (manual mode)")

    monkeypatch.setattr(UsMarketRefreshService, "refresh", _fake_refresh)

    app = FastAPI()
    try:
        await run_us_market_refresh_job(app)
        assert app.state.us_market_refresh_last_run_at is not None  # app.state 동작 보존
        async with job_session_factory() as session:
            run = (
                await session.execute(
                    select(SchedulerRun)
                    .where(SchedulerRun.job_id == US_MARKET_REFRESH_JOB_ID)
                    .order_by(SchedulerRun.id.desc())
                )
            ).scalars().first()
        assert run is not None, "us_market_refresh scheduler_run이 기록되지 않았다"
        assert run.status == SchedulerRunStatus.SUCCESS
        assert run.summary.get("provider") == "manual"
    finally:
        async with job_session_factory() as session:
            await session.execute(delete(SchedulerRun).where(SchedulerRun.job_id == US_MARKET_REFRESH_JOB_ID))
            await session.commit()


async def test_us_market_refresh_job_records_failure(job_session_factory, monkeypatch) -> None:
    """refresh가 실패하면 FAILED scheduler_run을 기록하고 last_error를 남긴다(에러를 숨기지 않음)."""
    from app.services.us_market_refresh_service import UsMarketRefreshService

    async def _boom(self):
        raise RuntimeError("FRED request failed")

    monkeypatch.setattr(UsMarketRefreshService, "refresh", _boom)

    app = FastAPI()
    try:
        await run_us_market_refresh_job(app)  # 예외가 밖으로 전파되면 안 된다
        assert app.state.us_market_refresh_last_error is not None  # 에러 보존
        async with job_session_factory() as session:
            run = (
                await session.execute(
                    select(SchedulerRun)
                    .where(SchedulerRun.job_id == US_MARKET_REFRESH_JOB_ID)
                    .order_by(SchedulerRun.id.desc())
                )
            ).scalars().first()
        assert run is not None
        assert run.status == SchedulerRunStatus.FAILED
        assert "FRED" in (run.error_message or "")
    finally:
        async with job_session_factory() as session:
            await session.execute(delete(SchedulerRun).where(SchedulerRun.job_id == US_MARKET_REFRESH_JOB_ID))
            await session.commit()


async def test_us_market_refresh_run_visible_to_scheduler_health_repo(job_session_factory, monkeypatch) -> None:
    """기록된 run이 SchedulerHealthService가 보는 SchedulerRunRepository.latest_by_job로 조회된다.

    이것이 '활성이나 실행 기록 없음' 오탐을 해소하는 핵심 — 활성 시 health가 이 run을 본다.
    """
    from app.domain.repositories.scheduler_run import SchedulerRunRepository
    from app.services.us_market_refresh_service import RefreshResult, UsMarketRefreshService

    async def _fake_refresh(self):
        return RefreshResult(provider="manual", updated=False, session_date=None, reason="manual")

    monkeypatch.setattr(UsMarketRefreshService, "refresh", _fake_refresh)

    try:
        await run_us_market_refresh_job(FastAPI())
        async with job_session_factory() as session:
            latest = await SchedulerRunRepository(session).latest_by_job(US_MARKET_REFRESH_JOB_ID)
        assert latest is not None
        assert latest.status == SchedulerRunStatus.SUCCESS
    finally:
        async with job_session_factory() as session:
            await session.execute(delete(SchedulerRun).where(SchedulerRun.job_id == US_MARKET_REFRESH_JOB_ID))
            await session.commit()
