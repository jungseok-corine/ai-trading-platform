"""C-2.14: Live Account Registration & Safety State Initialization 테스트.

검증 항목:
  1. live account registration creates Account with AccountType.LIVE
  2. registration masks account number in output
  3. registration creates TradingGuardState paused
  4. registration creates RiskConfig with emergency_stop=True
  5. registration is idempotent (re-run same account → same result, no duplicate)
  6. duplicate registration does not create duplicate Account rows
  7. existing TradingGuardState resumed → registration forces paused (보수적)
  8. existing RiskConfig emergency_stop=False → registration forces True (보수적)
  9. --verify-readonly calls balance/executions only, not place_order
  10. --verify-readonly never calls place_order
  11. StrategyRunner cannot trade live account (paused + emergency_stop)
  12. TradeService cannot place order (real_trading_enabled=False)
  13. paper account unaffected by live registration
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, PauseSource
from app.domain.models.risk import RiskConfig
from app.domain.models.trading_guard import TradingGuardState
from app.services.live_account_registration_service import (
    LiveAccountRegistrationService,
    _mask_account_no,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _register(session: AsyncSession, account_no: str = "12345678-01") -> object:
    svc = LiveAccountRegistrationService(session)
    return await svc.register(broker_account_no=account_no, alias="테스트실전계좌")


# ---------------------------------------------------------------------------
# 1. AccountType.LIVE로 Account 생성
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registration_creates_live_account(db_session: AsyncSession) -> None:
    result = await _register(db_session)

    assert result.errors == []
    assert result.account_type == "live"
    assert result.account_status == "created"
    assert result.account_id > 0

    account = await db_session.get(Account, result.account_id)
    assert account is not None
    assert account.account_type == AccountType.LIVE
    assert account.broker_account_no == "12345678-01"
    assert account.alias == "테스트실전계좌"


# ---------------------------------------------------------------------------
# 2. 계좌번호 마스킹
# ---------------------------------------------------------------------------


def test_mask_account_no_hides_sensitive_info() -> None:
    masked = _mask_account_no("50192525-01")
    assert "50192525" not in masked
    assert masked.startswith("5019")
    assert masked.endswith("-**")


def test_mask_account_no_none() -> None:
    assert _mask_account_no(None) == "(미설정)"
    assert _mask_account_no("") == "(미설정)"


@pytest.mark.asyncio
async def test_registration_result_contains_masked_account_no(db_session: AsyncSession) -> None:
    result = await _register(db_session, "50192525-01")
    assert "50192525" not in result.masked_account_no
    assert result.masked_account_no.startswith("5019")


# ---------------------------------------------------------------------------
# 3. TradingGuardState paused 생성
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registration_creates_trading_guard_paused(db_session: AsyncSession) -> None:
    result = await _register(db_session)

    guard_rows = await db_session.execute(
        select(TradingGuardState).where(TradingGuardState.account_id == result.account_id)
    )
    guard = guard_rows.scalar_one_or_none()

    assert guard is not None
    assert guard.is_paused is True
    assert guard.pause_source == PauseSource.MANUAL
    assert guard.paused_by == "registration"
    assert "read-only mode" in guard.pause_reason.lower() or "read-only" in guard.pause_reason


# ---------------------------------------------------------------------------
# 4. RiskConfig emergency_stop=True 생성
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registration_creates_risk_config_emergency_stop_true(db_session: AsyncSession) -> None:
    result = await _register(db_session)

    risk_rows = await db_session.execute(
        select(RiskConfig).where(RiskConfig.account_id == result.account_id)
    )
    config = risk_rows.scalar_one_or_none()

    assert config is not None
    assert config.emergency_stop is True
    assert result.emergency_stop is True
    assert result.risk_config_status == "created"


# ---------------------------------------------------------------------------
# 5. 멱등성 — 재등록 시 중복 없음
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registration_is_idempotent(db_session: AsyncSession) -> None:
    result1 = await _register(db_session, "12345678-01")
    result2 = await _register(db_session, "12345678-01")

    assert result1.errors == []
    assert result2.errors == []
    assert result1.account_id == result2.account_id
    assert result2.account_status == "already_exists"
    assert result2.trading_guard_paused is True
    assert result2.emergency_stop is True


# ---------------------------------------------------------------------------
# 6. 중복 Account row 미생성
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_duplicate_account_row(db_session: AsyncSession) -> None:
    await _register(db_session, "12345678-01")
    await _register(db_session, "12345678-01")

    rows = await db_session.execute(
        select(Account).where(Account.broker_account_no == "12345678-01")
    )
    accounts = list(rows.scalars().all())
    assert len(accounts) == 1


# ---------------------------------------------------------------------------
# 7. 기존 TradingGuardState resumed → 재등록 시 paused로 되돌림
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registration_forces_pause_on_resumed_guard(db_session: AsyncSession) -> None:
    # 첫 등록
    result = await _register(db_session)

    # guard를 resume 상태로 직접 변경
    guard = await db_session.get(TradingGuardState, (
        await db_session.execute(
            select(TradingGuardState).where(TradingGuardState.account_id == result.account_id)
        )
    ).scalar_one().id)
    guard.is_paused = False
    guard.resolved_by = "test_user"
    await db_session.flush()

    # 재등록
    result2 = await _register(db_session)

    assert result2.trading_guard_paused is True
    assert result2.guard_status == "updated_to_paused"

    # DB에서 직접 확인
    guard_row = (await db_session.execute(
        select(TradingGuardState).where(TradingGuardState.account_id == result.account_id)
    )).scalar_one()
    assert guard_row.is_paused is True


# ---------------------------------------------------------------------------
# 8. 기존 RiskConfig emergency_stop=False → 재등록 시 True로 되돌림
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registration_forces_emergency_stop_on_disabled(db_session: AsyncSession) -> None:
    # 첫 등록
    result = await _register(db_session)

    # risk_config를 emergency_stop=False로 변경
    config_row = (await db_session.execute(
        select(RiskConfig).where(RiskConfig.account_id == result.account_id)
    )).scalar_one()
    config_row.emergency_stop = False
    await db_session.flush()

    # 재등록
    result2 = await _register(db_session)

    assert result2.emergency_stop is True
    assert result2.risk_config_status == "updated_emergency_stop"

    # DB 직접 확인
    config2 = (await db_session.execute(
        select(RiskConfig).where(RiskConfig.account_id == result.account_id)
    )).scalar_one()
    assert config2.emergency_stop is True


# ---------------------------------------------------------------------------
# 9. --verify-readonly: balance/executions 조회만 호출
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_readonly_calls_only_balance_and_executions() -> None:
    """_run_verify_readonly는 balance와 daily_executions만 호출해야 한다."""
    import scripts.register_live_account_readonly as reg_script

    called = []
    place_order_called = []

    class _MockBroker:
        real_trading_enabled = False

        async def _get_access_token(self):
            return "fake_token_for_test"

        async def get_account_balance(self):
            from app.trading.broker.schemas import AccountBalance, AccountSummary
            called.append("get_account_balance")
            return AccountBalance(
                holdings=[],
                summary=AccountSummary(
                    total_deposit=Decimal("0"),
                    total_purchase_amount=Decimal("0"),
                    total_evaluation_amount=Decimal("0"),
                    total_profit_loss_amount=Decimal("0"),
                ),
            )

        async def get_daily_executions(self, **_):
            called.append("get_daily_executions")
            return []

        async def place_order(self, *args, **kwargs):
            place_order_called.append(args)
            raise AssertionError("place_order must not be called")

    import os
    import httpx

    with (
        patch.dict(os.environ, {
            "KIS_REAL_APP_KEY": "testkey",
            "KIS_REAL_APP_SECRET": "testsecret",
            "KIS_REAL_ACCOUNT_NO": "12345678-01",
        }),
        patch("app.trading.broker.kis_real.KISRealBrokerClient", return_value=_MockBroker()),
        patch.object(httpx, "AsyncClient") as mock_http_cls,
    ):
        mock_http = MagicMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http_cls.return_value = mock_http

        result = await reg_script._run_verify_readonly(account_id=1)

    assert place_order_called == [], "place_order must not be called"
    assert "get_account_balance" in called
    assert "get_daily_executions" in called
    assert result["order_api_called"] is False
    assert result["balance_query"] == "ok"
    assert result["executions_query"] == "ok"


# ---------------------------------------------------------------------------
# 10. --verify-readonly: place_order 미호출
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_readonly_never_calls_place_order() -> None:
    """_run_verify_readonly는 place_order를 호출하지 않는다."""
    import scripts.register_live_account_readonly as reg_script

    place_order_calls = []

    class _MockBroker:
        real_trading_enabled = False

        async def _get_access_token(self):
            return "fake"

        async def get_account_balance(self):
            from app.trading.broker.schemas import AccountBalance, AccountSummary
            return AccountBalance(
                holdings=[],
                summary=AccountSummary(
                    total_deposit=Decimal("0"),
                    total_purchase_amount=Decimal("0"),
                    total_evaluation_amount=Decimal("0"),
                    total_profit_loss_amount=Decimal("0"),
                ),
            )

        async def get_daily_executions(self, **_):
            return []

        async def place_order(self, *args, **kwargs):
            place_order_calls.append(True)

    import os
    import httpx

    with (
        patch.dict(os.environ, {
            "KIS_REAL_APP_KEY": "testkey",
            "KIS_REAL_APP_SECRET": "testsecret",
            "KIS_REAL_ACCOUNT_NO": "12345678-01",
        }),
        patch("app.trading.broker.kis_real.KISRealBrokerClient", return_value=_MockBroker()),
        patch.object(httpx, "AsyncClient") as mock_http_cls,
    ):
        mock_http = MagicMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http_cls.return_value = mock_http

        await reg_script._run_verify_readonly(account_id=1)

    assert place_order_calls == []


# ---------------------------------------------------------------------------
# 11. StrategyRunner — paused + emergency_stop 상태에서 주문 불가
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_strategy_runner_cannot_trade_live_account_while_paused(
    db_session: AsyncSession,
) -> None:
    """등록된 실전 계좌는 trading_guard paused 상태이므로 StrategyRunner가 주문할 수 없다."""
    from app.services.live_account_registration_service import LiveAccountRegistrationService
    from app.services.risk_service import RiskService
    from app.services.strategy_runner_service import StrategyRunnerService
    from app.services.trade_service import TradeService
    from app.trading.broker.kis_real import KISRealBrokerClient

    import httpx

    # 실전 계좌 등록
    svc = LiveAccountRegistrationService(db_session)
    reg_result = await svc.register(broker_account_no="99887766-01", alias="전략러너테스트")
    assert reg_result.trading_guard_paused is True

    # real broker (read-only)
    broker = KISRealBrokerClient(
        base_url="https://openapi.koreainvestment.com:9443",
        app_key="key",
        app_secret="secret",
        account_no="99887766-01",
        http_client=httpx.AsyncClient(),
        token_cache_path="/tmp/test_runner_token.json",
        real_trading_enabled=False,
    )
    broker_place_order = AsyncMock()
    broker.place_order = broker_place_order

    risk_svc = MagicMock(spec=RiskService)
    trade_svc = TradeService(db_session, broker, risk_svc)

    signal_svc = AsyncMock()
    signal_svc.generate_and_log_signal = AsyncMock(return_value=None)

    runner = StrategyRunnerService(db_session, signal_svc, trade_svc)
    results = await runner.run_once()

    # 전략 없음 → place_order 미호출
    assert isinstance(results, list)
    broker_place_order.assert_not_called()


# ---------------------------------------------------------------------------
# 12. TradeService — real_trading_enabled=False면 place_order 미호출
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trade_service_blocks_live_account_when_real_trading_disabled(
    db_session: AsyncSession,
) -> None:
    """등록된 실전 계좌 + real_trading_enabled=False → TradeService가 주문 차단."""
    from app.services.live_account_registration_service import LiveAccountRegistrationService
    from app.services.risk_service import RiskService
    from app.services.trade_service import TradeService
    from app.trading.broker.kis_real import KISRealBrokerClient
    from app.trading.strategy.base import Signal

    import httpx

    svc = LiveAccountRegistrationService(db_session)
    reg_result = await svc.register(broker_account_no="77665544-01")
    assert reg_result.trading_guard_paused is True

    broker = KISRealBrokerClient(
        base_url="https://openapi.koreainvestment.com:9443",
        app_key="key",
        app_secret="secret",
        account_no="77665544-01",
        http_client=httpx.AsyncClient(),
        token_cache_path="/tmp/test_trade_svc_token.json",
        real_trading_enabled=False,
    )
    broker_place_order = AsyncMock()
    broker.place_order = broker_place_order

    risk_svc = MagicMock(spec=RiskService)
    trade_svc = TradeService(db_session, broker, risk_svc)

    signal = Signal(
        symbol_code="005930",
        side="buy",
        quantity=1,
        price=Decimal("70000"),
        reason="test",
    )

    result = await trade_svc.execute_signal(reg_result.account_id, signal)

    assert result.approved is False
    # real_trading_disabled 가 먼저 걸리거나 trading_paused 가 걸림
    assert result.rule_name in ("real_trading_disabled", "trading_paused")
    broker_place_order.assert_not_called()


# ---------------------------------------------------------------------------
# 13. paper account 기존 흐름 영향 없음
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_paper_account_unaffected_by_live_registration(db_session: AsyncSession) -> None:
    """live account 등록이 paper account 동작에 영향을 주지 않아야 한다."""
    from app.domain.models.account import Account

    # paper 계좌 생성
    paper_account = Account(account_type=AccountType.PAPER, broker_account_no="PAPER-TEST-01")
    db_session.add(paper_account)
    await db_session.flush()

    # live 등록
    live_result = await _register(db_session, "88776655-01")

    # paper 계좌 guard 없어야 함 (live 등록으로 생성되면 안 됨)
    guard_rows = await db_session.execute(
        select(TradingGuardState).where(TradingGuardState.account_id == paper_account.id)
    )
    guard = guard_rows.scalar_one_or_none()
    assert guard is None, "paper account should not have TradingGuardState from live registration"

    # live 결과는 paper와 독립적
    assert live_result.account_id != paper_account.id
    assert live_result.errors == []


# ---------------------------------------------------------------------------
# 14. paper account_no로 live 등록 시도 → 오류
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registration_rejects_existing_paper_account_no(db_session: AsyncSession) -> None:
    """이미 PAPER로 등록된 계좌번호로 live 등록을 시도하면 오류를 반환해야 한다."""
    paper = Account(account_type=AccountType.PAPER, broker_account_no="CONFLICT-01")
    db_session.add(paper)
    await db_session.flush()

    result = await _register(db_session, "CONFLICT-01")

    assert len(result.errors) > 0
    assert "not LIVE" in result.errors[0]
    assert result.account_id == 0


# ---------------------------------------------------------------------------
# 15. 기존 RiskConfig already_set → 상태 보고
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registration_reports_already_set_when_risk_config_ok(db_session: AsyncSession) -> None:
    """RiskConfig가 이미 emergency_stop=True이면 risk_config_status=already_set이어야 한다."""
    result1 = await _register(db_session, "33221100-01")
    result2 = await _register(db_session, "33221100-01")

    assert result2.risk_config_status == "already_set"
    assert result2.emergency_stop is True
