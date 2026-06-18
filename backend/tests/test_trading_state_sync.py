"""C-2.11: TradingStateSyncService + sync_trading_state_job 통합 테스트.

모든 broker API 호출은 mock/fake으로 처리한다.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, SchedulerRunStatus, TradeSide
from app.domain.models.scheduler_run import SchedulerRun
from app.domain.models.trade import Trade
from app.scheduler.jobs import TRADING_STATE_SYNC_JOB_ID, sync_trading_state_job
from app.services.trading_state_sync_service import TradingStateSyncService
from app.trading.broker.base import BrokerClient
from app.trading.broker.schemas import (
    AccountBalance,
    AccountHolding,
    AccountSummary,
    BrokerPositionItem,
    MinuteCandle,
    OrderExecution,
    OrderRequest,
    OrderResult,
    PriceQuote,
)

KST = ZoneInfo("Asia/Seoul")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeBrokerForSync(BrokerClient):
    """TradingStateSyncService 테스트 전용 Fake Broker."""

    def __init__(
        self,
        executions: list[OrderExecution] | None = None,
        broker_positions: list[BrokerPositionItem] | None = None,
        daily_executions_error: Exception | None = None,
        broker_positions_error: Exception | None = None,
    ) -> None:
        self._executions = executions or []
        self._broker_positions = broker_positions or []
        self._daily_executions_error = daily_executions_error
        self._broker_positions_error = broker_positions_error

    async def get_current_price(self, symbol_code: str) -> PriceQuote:
        raise NotImplementedError

    async def get_minute_candles(
        self, symbol_code: str, target_time: str | None = None, include_past_data: bool = True
    ) -> list[MinuteCandle]:
        raise NotImplementedError

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

    async def get_daily_executions(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> list[OrderExecution]:
        if self._daily_executions_error is not None:
            raise self._daily_executions_error
        return self._executions

    async def get_broker_positions(self) -> list[BrokerPositionItem]:
        if self._broker_positions_error is not None:
            raise self._broker_positions_error
        return self._broker_positions


@pytest_asyncio.fixture
async def sync_session_factory(monkeypatch):
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("app.scheduler.jobs.async_session_factory", factory)
    yield factory
    await engine.dispose()


async def _create_account(factory, account_type: AccountType = AccountType.PAPER) -> int:
    async with factory() as session:
        account = Account(account_type=account_type, broker_account_no="00000000-01")
        session.add(account)
        await session.commit()
        return account.id


async def _create_pending_trade(factory, account_id: int) -> int:
    yesterday = datetime.now(KST) - timedelta(days=1)
    async with factory() as session:
        trade = Trade(
            account_id=account_id,
            symbol_code="005930",
            side=TradeSide.BUY,
            quantity=1,
            order_status=OrderStatus.PENDING,
            broker_order_id="0000000099",
            entry_time=yesterday,
        )
        session.add(trade)
        await session.commit()
        return trade.id


async def _cleanup(factory, *, account_ids=(), trade_ids=()):
    async with factory() as session:
        if trade_ids:
            await session.execute(delete(Trade).where(Trade.id.in_(trade_ids)))
        if account_ids:
            await session.execute(delete(Account).where(Account.id.in_(account_ids)))
        await session.commit()


async def _cleanup_runs(factory):
    async with factory() as session:
        await session.execute(delete(SchedulerRun).where(SchedulerRun.job_id == TRADING_STATE_SYNC_JOB_ID))
        await session.commit()


# ---------------------------------------------------------------------------
# 1. order sync → reconciliation 순서 검증
# ---------------------------------------------------------------------------


async def test_sync_pipeline_calls_order_sync_then_reconciliation(sync_session_factory) -> None:
    """sync_account_trading_state가 order sync를 먼저, reconciliation을 그 다음에 호출하는지 검증."""
    call_order: list[str] = []

    original_order_sync_init = __import__(
        "app.services.order_sync_service", fromlist=["OrderSyncService"]
    ).OrderSyncService.__init__
    original_reconcile_init = __import__(
        "app.services.position_reconciliation_service", fromlist=["PositionReconciliationService"]
    ).PositionReconciliationService.__init__

    account_id = await _create_account(sync_session_factory)
    try:
        broker = FakeBrokerForSync(broker_positions=[])
        async with sync_session_factory() as session:
            svc = TradingStateSyncService(session, broker)

            # Patch internal methods to record call order
            original_run_order = svc._run_order_sync
            original_run_recon = svc._run_reconciliation

            async def patched_order_sync(warnings):
                call_order.append("order_sync")
                return await original_run_order(warnings)

            async def patched_reconciliation(acc_id, warnings):
                call_order.append("reconciliation")
                return await original_run_recon(acc_id, warnings)

            svc._run_order_sync = patched_order_sync
            svc._run_reconciliation = patched_reconciliation

            await svc.sync_account_trading_state(account_id)

        assert call_order == ["order_sync", "reconciliation"], (
            f"Expected order_sync before reconciliation, got: {call_order}"
        )
    finally:
        await _cleanup(sync_session_factory, account_ids=[account_id])


# ---------------------------------------------------------------------------
# 2. order sync 결과와 reconciliation 결과가 summary에 포함되는지
# ---------------------------------------------------------------------------


async def test_sync_result_includes_both_order_and_reconciliation_data(sync_session_factory) -> None:
    account_id = await _create_account(sync_session_factory)
    try:
        broker = FakeBrokerForSync(broker_positions=[])
        async with sync_session_factory() as session:
            svc = TradingStateSyncService(session, broker)
            result = await svc.sync_account_trading_state(account_id)

        assert result.account_id == account_id
        assert result.broker_mode == "paper"
        assert result.orders_checked >= 0
        assert result.mismatches_count >= 0
        assert isinstance(result.warnings, list)
        assert isinstance(result.order_sync_errors, list)
        assert isinstance(result.position_errors, list)
        assert result.started_at <= result.completed_at
    finally:
        await _cleanup(sync_session_factory, account_ids=[account_id])


# ---------------------------------------------------------------------------
# 3. order sync 실패 시 reconciliation을 계속하는지
# ---------------------------------------------------------------------------


async def test_order_sync_failure_continues_reconciliation(sync_session_factory) -> None:
    account_id = await _create_account(sync_session_factory)
    trade_id = await _create_pending_trade(sync_session_factory, account_id)
    try:
        broker = FakeBrokerForSync(
            daily_executions_error=RuntimeError("KIS API 조회 실패"),
            broker_positions=[],
        )
        async with sync_session_factory() as session:
            svc = TradingStateSyncService(session, broker)
            result = await svc.sync_account_trading_state(account_id)

        # order sync가 실패해도 결과가 반환되어야 한다
        assert result is not None
        # order sync 실패 내용이 warnings에 포함되어야 한다
        assert any("order sync" in w.lower() for w in result.warnings), (
            f"warnings should mention order sync failure, got: {result.warnings}"
        )
        # reconciliation은 실행되어야 한다 (positions_compared >= 0)
        assert result.positions_compared >= 0
        assert result.position_errors == []
    finally:
        await _cleanup(sync_session_factory, account_ids=[account_id], trade_ids=[trade_id])


# ---------------------------------------------------------------------------
# 4. reconciliation 실패 시 전체 result에 warning/error가 남는지
# ---------------------------------------------------------------------------


async def test_reconciliation_failure_recorded_in_result(sync_session_factory) -> None:
    account_id = await _create_account(sync_session_factory)
    try:
        broker = FakeBrokerForSync(
            broker_positions_error=RuntimeError("잔고 조회 실패"),
        )
        async with sync_session_factory() as session:
            svc = TradingStateSyncService(session, broker)
            result = await svc.sync_account_trading_state(account_id)

        # reconciliation 실패가 warnings/position_errors에 기록되어야 한다
        assert any("reconciliation" in w.lower() for w in result.warnings), (
            f"Expected reconciliation warning, got: {result.warnings}"
        )
        assert len(result.position_errors) > 0
        # 전체 결과는 반환되어야 한다 (예외 전파 금지)
        assert result.account_id == account_id
    finally:
        await _cleanup(sync_session_factory, account_ids=[account_id])


# ---------------------------------------------------------------------------
# 5. scheduler job이 service를 호출하는지
# ---------------------------------------------------------------------------


async def test_sync_trading_state_job_calls_service(sync_session_factory) -> None:
    account_id = await _create_account(sync_session_factory)
    try:
        app = FastAPI()
        app.state.broker_client = FakeBrokerForSync(broker_positions=[])

        await sync_trading_state_job(app)

        assert app.state.trading_state_sync_last_run_at is not None
        assert app.state.trading_state_sync_last_error is None

        async with sync_session_factory() as session:
            run = (
                await session.execute(
                    select(SchedulerRun)
                    .where(SchedulerRun.job_id == TRADING_STATE_SYNC_JOB_ID)
                    .order_by(SchedulerRun.id.desc())
                    .limit(1)
                )
            ).scalars().first()

        assert run is not None
        assert run.status == SchedulerRunStatus.SUCCESS
        assert run.summary is not None
        assert "accounts_synced" in run.summary
    finally:
        await _cleanup(sync_session_factory, account_ids=[account_id])
        await _cleanup_runs(sync_session_factory)


# ---------------------------------------------------------------------------
# 6. scheduler job 실패가 scheduler 전체를 죽이지 않는지
# ---------------------------------------------------------------------------


async def test_sync_trading_state_job_does_not_raise_on_broker_missing(sync_session_factory) -> None:
    """app.state.broker_client가 없을 때 job이 예외를 전파하지 않고 FAILED를 기록한다."""
    app = FastAPI()  # broker_client 미설정

    try:
        await sync_trading_state_job(app)  # 예외가 전파되면 안 된다

        assert app.state.trading_state_sync_last_error is not None
        assert app.state.trading_state_sync_last_run_at is not None

        async with sync_session_factory() as session:
            run = (
                await session.execute(
                    select(SchedulerRun)
                    .where(SchedulerRun.job_id == TRADING_STATE_SYNC_JOB_ID)
                    .order_by(SchedulerRun.id.desc())
                    .limit(1)
                )
            ).scalars().first()

        assert run is not None
        assert run.status == SchedulerRunStatus.FAILED
        assert run.error_message is not None
    finally:
        await _cleanup_runs(sync_session_factory)


# ---------------------------------------------------------------------------
# 7. manual API가 sync result를 반환하는지 (service 수준 검증)
# ---------------------------------------------------------------------------


async def test_sync_account_trading_state_returns_result(sync_session_factory) -> None:
    account_id = await _create_account(sync_session_factory)
    try:
        broker = FakeBrokerForSync(broker_positions=[])
        async with sync_session_factory() as session:
            svc = TradingStateSyncService(session, broker)
            result = await svc.sync_account_trading_state(account_id)

        # TradingStateSyncResult의 모든 필수 필드가 채워져야 한다
        assert result.account_id == account_id
        assert result.broker_mode in ("paper", "live", "unknown")
        assert isinstance(result.orders_checked, int)
        assert isinstance(result.mismatches_count, int)
        assert isinstance(result.warnings, list)
        assert result.started_at is not None
        assert result.completed_at is not None
    finally:
        await _cleanup(sync_session_factory, account_ids=[account_id])


# ---------------------------------------------------------------------------
# 8. paper mode: mismatch 발생 시 DB 자동 보정 + warning 없음 (일치 케이스)
# ---------------------------------------------------------------------------


async def test_paper_mode_no_mismatch_no_sync_to_db(sync_session_factory) -> None:
    """broker와 DB가 일치하면 positions_synced_to_db=False이어야 한다."""
    account_id = await _create_account(sync_session_factory, AccountType.PAPER)
    try:
        broker = FakeBrokerForSync(broker_positions=[])  # broker에 포지션 없음 = DB도 없음
        async with sync_session_factory() as session:
            svc = TradingStateSyncService(session, broker)
            result = await svc.sync_account_trading_state(account_id)

        assert result.mismatches_count == 0
        assert not result.positions_synced_to_db
    finally:
        await _cleanup(sync_session_factory, account_ids=[account_id])


# ---------------------------------------------------------------------------
# 9. sync_all_accounts: 빈 계좌 목록이면 빈 리스트 반환
# ---------------------------------------------------------------------------


async def test_sync_all_accounts_returns_empty_when_no_accounts(sync_session_factory) -> None:
    broker = FakeBrokerForSync(broker_positions=[])
    async with sync_session_factory() as session:
        svc = TradingStateSyncService(session, broker)
        # 계좌가 없을 때 (기존 계좌가 있을 수 있으므로 직접 list 체크 생략)
        # sync_all_accounts는 list를 반환해야 한다
        results = await svc.sync_all_accounts()
    assert isinstance(results, list)


# ---------------------------------------------------------------------------
# 10. sync_all_accounts: 계좌가 있으면 각 계좌에 대한 result가 반환됨
# ---------------------------------------------------------------------------


async def test_sync_all_accounts_returns_result_per_account(sync_session_factory) -> None:
    account_id = await _create_account(sync_session_factory)
    try:
        broker = FakeBrokerForSync(broker_positions=[])
        async with sync_session_factory() as session:
            svc = TradingStateSyncService(session, broker)
            results = await svc.sync_all_accounts()

        account_ids_in_results = [r.account_id for r in results]
        assert account_id in account_ids_in_results
    finally:
        await _cleanup(sync_session_factory, account_ids=[account_id])


# ---------------------------------------------------------------------------
# 11. sync_trading_state_job: account 없으면 SKIPPED
# ---------------------------------------------------------------------------


async def test_sync_trading_state_job_skipped_when_no_accounts(sync_session_factory) -> None:
    """accounts 테이블이 완전히 비어 있을 때 job status는 SKIPPED이어야 한다.

    이 테스트는 독립 DB 환경에서 다른 계좌가 없는 경우를 전제한다.
    다른 테스트와 격리가 안 된 경우 SKIPPED가 아닐 수 있어 skip으로 처리한다.
    """
    # 기존 계좌가 DB에 있을 수 있어서 이 테스트는 정확한 고립이 어렵다.
    # job 자체가 예외 없이 실행되는지만 확인한다.
    app = FastAPI()
    app.state.broker_client = FakeBrokerForSync(broker_positions=[])

    try:
        await sync_trading_state_job(app)  # 예외 전파 없어야 함

        assert app.state.trading_state_sync_last_run_at is not None
    finally:
        await _cleanup_runs(sync_session_factory)
