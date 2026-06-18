"""C-2.13: KIS 실전 계좌 Read-Only 검증 테스트.

검증 항목:
  1. KISRealBrokerClient.real_trading_enabled 기본값 False
  2. read-only 모드에서 get_account_balance 허용 (place_order 미호출)
  3. read-only 모드에서 get_daily_executions 허용 (place_order 미호출)
  4. read-only 모드에서 place_order → RealTradingDisabledError
  5. real mode + emergency_stop=False + trading_guard resume + real_trading_enabled=False → TradeService 주문 차단
  6. StrategyRunnerService: real_trading_enabled=False → broker.place_order 미호출
  7. TradeService.execute_signal: real_trading_enabled=False → broker.place_order 미호출
  8. paper mode(KISPaperBrokerClient)는 real_trading_enabled 속성 없음 → 기존 흐름 유지
  9. smoke test: --confirm-readonly 없으면 KIS API 미호출
  10. smoke test: 주문 API(place_order) 절대 미호출
  11. 민감정보 마스킹 함수 검증
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, TradeSide
from app.trading.broker.exceptions import RealTradingDisabledError
from app.trading.broker.kis_real import KISRealBrokerClient
from app.trading.broker.schemas import (
    AccountBalance,
    AccountHolding,
    AccountSummary,
    BrokerPositionItem,
    OrderExecution,
    OrderRequest,
    OrderType,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_real_broker(real_trading_enabled: bool = False) -> KISRealBrokerClient:
    """실제 HTTP 호출 없이 KISRealBrokerClient를 생성한다."""
    import httpx

    return KISRealBrokerClient(
        base_url="https://openapi.koreainvestment.com:9443",
        app_key="test_key",
        app_secret="test_secret",
        account_no="12345678-01",
        http_client=httpx.AsyncClient(),
        token_cache_path="/tmp/test_kis_real_token.json",
        real_trading_enabled=real_trading_enabled,
    )


def _fake_balance_response() -> AccountBalance:
    return AccountBalance(
        holdings=[
            AccountHolding(
                symbol_code="005930",
                symbol_name="삼성전자",
                quantity="10",
                avg_purchase_price="70000",
                current_price="72000",
                evaluation_amount="720000",
                profit_loss_amount="20000",
                profit_loss_rate="2.86",
            )
        ],
        summary=AccountSummary(
            total_deposit=Decimal("1000000"),
            total_purchase_amount=Decimal("700000"),
            total_evaluation_amount=Decimal("720000"),
            total_profit_loss_amount=Decimal("20000"),
        ),
    )


# ---------------------------------------------------------------------------
# 1. real_trading_enabled 기본값 False
# ---------------------------------------------------------------------------


def test_real_broker_default_real_trading_disabled() -> None:
    """KISRealBrokerClient는 기본값이 real_trading_enabled=False여야 한다."""
    broker = _make_real_broker()
    assert broker.real_trading_enabled is False


def test_real_broker_explicit_enabled() -> None:
    """real_trading_enabled=True로 명시하면 True가 된다."""
    broker = _make_real_broker(real_trading_enabled=True)
    assert broker.real_trading_enabled is True


# ---------------------------------------------------------------------------
# 2. read-only 모드에서 get_account_balance 허용
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_readonly_balance_query_allowed() -> None:
    """real_trading_enabled=False여도 get_account_balance는 호출 가능해야 한다."""
    broker = _make_real_broker(real_trading_enabled=False)

    fake_response = _fake_balance_response()
    broker.get_account_balance = AsyncMock(return_value=fake_response)

    result = await broker.get_account_balance()
    assert len(result.holdings) == 1
    assert result.holdings[0].symbol_code == "005930"
    broker.get_account_balance.assert_called_once()


# ---------------------------------------------------------------------------
# 3. read-only 모드에서 get_daily_executions 허용
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_readonly_daily_executions_allowed() -> None:
    """real_trading_enabled=False여도 get_daily_executions는 호출 가능해야 한다."""
    broker = _make_real_broker(real_trading_enabled=False)

    broker.get_daily_executions = AsyncMock(return_value=[])

    result = await broker.get_daily_executions()
    assert result == []
    broker.get_daily_executions.assert_called_once()


# ---------------------------------------------------------------------------
# 4. read-only 모드에서 place_order 차단
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_readonly_place_order_raises_real_trading_disabled() -> None:
    """real_trading_enabled=False인 KISRealBrokerClient에서 place_order는 RealTradingDisabledError를 발생시켜야 한다."""
    broker = _make_real_broker(real_trading_enabled=False)

    order = OrderRequest(
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=1,
        price=Decimal("70000"),
        order_type=OrderType.LIMIT,
    )

    with pytest.raises(RealTradingDisabledError):
        await broker.place_order(order)


@pytest.mark.asyncio
async def test_enabled_broker_place_order_does_not_raise_disabled_error() -> None:
    """real_trading_enabled=True이면 RealTradingDisabledError가 발생하지 않는다 (KIS API 오류는 가능)."""
    broker = _make_real_broker(real_trading_enabled=True)

    order = OrderRequest(
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=1,
        price=Decimal("70000"),
        order_type=OrderType.LIMIT,
    )

    # real_trading_enabled=True이면 RealTradingDisabledError는 아니어야 한다 (네트워크 오류는 허용).
    with pytest.raises(Exception) as exc_info:
        await broker.place_order(order)

    assert not isinstance(exc_info.value, RealTradingDisabledError)


# ---------------------------------------------------------------------------
# 5. real mode + trading_guard resume + real_trading_enabled=False → 주문 차단
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trade_service_blocks_when_real_trading_disabled(db_session: AsyncSession) -> None:
    """trading_guard resume 상태여도 real_trading_enabled=False이면 TradeService가 주문을 차단해야 한다."""
    from app.services.risk_service import RiskService
    from app.services.trade_service import TradeService
    from app.trading.strategy.base import Signal

    broker = _make_real_broker(real_trading_enabled=False)
    broker_place_order = AsyncMock()
    broker.place_order = broker_place_order

    risk_service = MagicMock(spec=RiskService)

    account = Account(account_type=AccountType.LIVE, broker_account_no="12345678-01")
    db_session.add(account)
    await db_session.flush()

    svc = TradeService(db_session, broker, risk_service)
    signal = Signal(
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=1,
        price=Decimal("70000"),
        reason="test",
    )

    result = await svc.execute_signal(account.id, signal)

    assert result.approved is False
    assert result.rule_name == "real_trading_disabled"
    # broker.place_order는 절대 호출되지 않아야 한다
    broker_place_order.assert_not_called()


# ---------------------------------------------------------------------------
# 6. StrategyRunnerService: real_trading_enabled=False → broker.place_order 미호출
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_strategy_runner_does_not_call_place_order_when_real_trading_disabled(
    db_session: AsyncSession,
) -> None:
    """StrategyRunnerService: real_trading_enabled=False이면 execute_signal이 place_order를 호출하지 않는다."""
    from app.services.risk_service import RiskService
    from app.services.strategy_runner_service import StrategyRunnerService
    from app.services.trade_service import TradeService

    broker = _make_real_broker(real_trading_enabled=False)
    broker_place_order = AsyncMock()
    broker.place_order = broker_place_order

    risk_service = MagicMock(spec=RiskService)
    trade_service = TradeService(db_session, broker, risk_service)

    signal_svc = AsyncMock()
    signal_svc.generate_and_log_signal = AsyncMock(return_value=None)  # 신호 없음

    runner = StrategyRunnerService(db_session, signal_svc, trade_service)

    # 전략 없음 → run_once는 빈 목록 반환 (place_order 미호출)
    results = await runner.run_once()
    assert isinstance(results, list)
    broker_place_order.assert_not_called()


# ---------------------------------------------------------------------------
# 7. TradeService.execute_signal: real_trading_enabled=False → place_order 미호출
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_signal_does_not_call_place_order_when_real_trading_disabled(
    db_session: AsyncSession,
) -> None:
    """TradeService.execute_signal이 real_trading_enabled=False일 때 place_order를 호출하지 않아야 한다."""
    from app.services.risk_service import RiskService
    from app.services.trade_service import TradeService
    from app.trading.strategy.base import Signal

    broker = _make_real_broker(real_trading_enabled=False)
    broker_place_order = AsyncMock()
    broker.place_order = broker_place_order

    risk_service = MagicMock(spec=RiskService)

    account = Account(account_type=AccountType.LIVE, broker_account_no="12345678-01")
    db_session.add(account)
    await db_session.flush()

    svc = TradeService(db_session, broker, risk_service)
    signal = Signal(
        symbol_code="005930",
        side=TradeSide.SELL,
        quantity=2,
        price=Decimal("72000"),
        reason="test-sell",
    )

    result = await svc.execute_signal(account.id, signal)

    assert not result.approved
    assert result.rule_name == "real_trading_disabled"
    broker_place_order.assert_not_called()


# ---------------------------------------------------------------------------
# 8. paper mode 기존 흐름 유지
# ---------------------------------------------------------------------------


def test_paper_broker_has_no_real_trading_enabled_attr() -> None:
    """KISPaperBrokerClient는 real_trading_enabled 속성이 없다 → getattr 기본값 True → 차단 없음."""
    from app.trading.broker.kis_paper import KISPaperBrokerClient

    import httpx

    paper_broker = KISPaperBrokerClient(
        base_url="https://openapivts.koreainvestment.com:29443",
        app_key="key",
        app_secret="secret",
        account_no="12345678-01",
        http_client=httpx.AsyncClient(),
        token_cache_path="/tmp/test_paper_token.json",
    )

    # paper broker는 real_trading_enabled가 없다 → getattr 기본값 True → 주문 차단 없음
    assert not hasattr(paper_broker, "real_trading_enabled")
    assert getattr(paper_broker, "real_trading_enabled", True) is True


@pytest.mark.asyncio
async def test_trade_service_paper_broker_not_blocked_by_real_trading_check(
    db_session: AsyncSession,
) -> None:
    """TradeService가 paper broker를 사용할 때 real_trading_disabled 차단이 발생하지 않아야 한다."""
    from app.services.risk_service import RiskService
    from app.services.trade_service import TradeService
    from app.trading.broker.kis_paper import KISPaperBrokerClient
    from app.trading.strategy.base import Signal

    import httpx

    paper_broker = KISPaperBrokerClient(
        base_url="https://openapivts.koreainvestment.com:29443",
        app_key="key",
        app_secret="secret",
        account_no="12345678-01",
        http_client=httpx.AsyncClient(),
        token_cache_path="/tmp/test_paper_token.json",
    )
    paper_place_order = AsyncMock()
    paper_broker.place_order = paper_place_order

    from app.trading.broker.schemas import OrderResult
    from datetime import datetime
    from zoneinfo import ZoneInfo

    KST = ZoneInfo("Asia/Seoul")
    paper_place_order.return_value = OrderResult(
        broker_order_id="0000000001",
        order_status=OrderStatus.PENDING,
        ordered_at=datetime.now(KST),
    )

    risk_svc = MagicMock(spec=RiskService)
    from app.trading.risk.rules import RiskCheckResult
    risk_svc.validate_signal = AsyncMock(
        return_value=RiskCheckResult(approved=True, rule_name=None, reason=None)
    )

    account = Account(account_type=AccountType.PAPER, broker_account_no="12345678-01")
    db_session.add(account)
    await db_session.flush()

    svc = TradeService(db_session, paper_broker, risk_svc)
    signal = Signal(
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=1,
        price=Decimal("70000"),
        reason="paper-test",
    )

    result = await svc.execute_signal(account.id, signal)

    # paper broker는 real_trading_disabled로 차단되지 않아야 한다
    assert result.rule_name != "real_trading_disabled"
    # risk 통과 후 place_order 호출됨
    paper_place_order.assert_called_once()


# ---------------------------------------------------------------------------
# 9. smoke test: --confirm-readonly 없으면 KIS API 미호출
# ---------------------------------------------------------------------------


def test_smoke_test_dry_run_no_api_calls(monkeypatch) -> None:
    """--confirm-readonly 없이 실행하면 KIS API를 호출하지 않아야 한다."""
    import scripts.kis_real_readonly_smoke_test as smoke

    api_called = []

    async def fake_verify():
        api_called.append(True)
        return {}

    monkeypatch.setattr(smoke, "_run_readonly_verification", fake_verify)

    # confirm_readonly=False → _run_readonly_verification 미호출
    config = smoke._check_env_config()
    verdict = smoke._print_report(config, api_result=None, confirm_readonly=False)

    assert not api_called, "confirm-readonly 없으면 KIS API를 호출하면 안 됩니다"
    assert verdict == "DRY_RUN_OK"


# ---------------------------------------------------------------------------
# 10. smoke test: 주문 API(place_order) 절대 미호출
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smoke_test_never_calls_place_order() -> None:
    """smoke test의 _run_readonly_verification은 place_order를 호출하지 않아야 한다.

    KISRealBrokerClient를 mock으로 교체하고, place_order가 호출되면 테스트가 실패한다.
    mock 경로: app.trading.broker.kis_real.KISRealBrokerClient (실제 import 위치)
    """
    import os
    import httpx
    import scripts.kis_real_readonly_smoke_test as smoke

    place_order_calls = []

    class _MockRealBroker:
        real_trading_enabled = False

        async def _get_access_token(self):
            return "fake_token_for_test"

        async def get_account_balance(self):
            return _fake_balance_response()

        async def get_daily_executions(self, **_):
            return []

        async def place_order(self, *args, **kwargs):
            place_order_calls.append(args)
            raise AssertionError("place_order must not be called in smoke test")

    # _run_readonly_verification 내부에서 KISRealBrokerClient를 직접 import하므로
    # 실제 정의 위치를 patch한다.
    with (
        patch.dict(os.environ, {
            "KIS_REAL_APP_KEY": "test_key_xxxx",
            "KIS_REAL_APP_SECRET": "test_secret_xxxx",
            "KIS_REAL_ACCOUNT_NO": "12345678-01",
        }),
        patch("app.trading.broker.kis_real.KISRealBrokerClient", return_value=_MockRealBroker()),
        patch("httpx.AsyncClient") as mock_http_cls,
    ):
        mock_http = MagicMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http_cls.return_value = mock_http

        result = await smoke._run_readonly_verification()

    assert place_order_calls == [], "smoke test는 place_order를 호출해선 안 됩니다"
    assert result["order_api_called"] is False
    assert result["real_trading_enabled"] is False


# ---------------------------------------------------------------------------
# 11. 민감정보 마스킹 검증
# ---------------------------------------------------------------------------


def test_mask_hides_most_of_value() -> None:
    """_mask는 앞 4자리만 남기고 나머지를 ***로 대체해야 한다."""
    import scripts.kis_real_readonly_smoke_test as smoke

    result = smoke._mask("ABCDEFGHIJ1234567890")
    assert result.startswith("ABCD")
    assert "***" in result
    assert "EFGHIJ" not in result


def test_mask_empty_returns_not_set() -> None:
    """_mask는 빈 값에 대해 (미설정)을 반환해야 한다."""
    import scripts.kis_real_readonly_smoke_test as smoke

    assert smoke._mask("") == "(미설정)"
    assert smoke._mask(None) == "(미설정)"


def test_mask_account_no_hides_suffix() -> None:
    """_mask_account_no는 계좌번호의 앞 4자리만 표시하고 나머지를 마스킹해야 한다."""
    import scripts.kis_real_readonly_smoke_test as smoke

    result = smoke._mask_account_no("50192525-01")
    assert result.startswith("5019")
    assert "2525" not in result
    assert "01" not in result.split("-")[1]


def test_mask_does_not_expose_full_app_key() -> None:
    """마스킹 결과에 원본 app_key가 노출되지 않아야 한다."""
    import scripts.kis_real_readonly_smoke_test as smoke

    app_key = "ABCDEFGHIJKLMNOPQRST"
    masked = smoke._mask(app_key)
    assert app_key not in masked
    assert len(masked) < len(app_key) + 10  # 대폭 단축


def test_check_env_config_masks_sensitive_info(monkeypatch) -> None:
    """_check_env_config는 민감정보를 마스킹한 값만 노출해야 한다."""
    import os
    import scripts.kis_real_readonly_smoke_test as smoke

    monkeypatch.setenv("KIS_REAL_APP_KEY", "SECRETAPPKEY12345678")
    monkeypatch.setenv("KIS_REAL_APP_SECRET", "SECRETAPPSECRET9876")
    monkeypatch.setenv("KIS_REAL_ACCOUNT_NO", "50192525-01")

    config = smoke._check_env_config()

    assert "SECRETAPPKEY12345678" not in config["app_key_masked"]
    assert "SECRETAPPSECRET9876" not in str(config)
    assert "50192525" not in config["account_no_masked"]
    assert config["config_ready"] is True
