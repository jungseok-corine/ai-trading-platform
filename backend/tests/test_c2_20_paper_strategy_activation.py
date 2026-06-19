"""C-2.20 Paper Strategy Activation 테스트 (13개).

테스트 범주:
  C-1. runner 인식 조건 (2): list_active() 가 TESTING 인식 / DRAFT 미인식
  B.   스크립트 동작 (3): dry-run DB 무변경 / --apply 생성+TESTING / 멱등성
  E-1. signal 생성 fixture (4): volume BUY+indicators / flow BUY+context / flow 전체 indicators
  E-2. 실 DB 데이터 관찰 (1): 시드 데이터 기반 end-to-end
  F.   주문 미실행 (3): auto_trade_enabled=false / place_order 미호출 / guard pause
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import (
    AccountType,
    OrderStatus,
    PauseSource,
    StrategyVersionStatus,
)
from app.domain.models.investor_flow import InvestorFlow
from app.domain.models.risk import RiskConfig
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.trading_guard import TradingGuardState
from app.domain.repositories.investor_flow import InvestorFlowRepository
from app.domain.repositories.strategy import StrategyVersionRepository
from app.services.market_data_service import MarketDataService
from app.services.risk_service import RiskService
from app.services.signal_service import SignalService
from app.services.strategy_runner_service import StrategyRunnerService
from app.services.trade_service import TradeService
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

# ---------------------------------------------------------------------------
# 헬퍼: 캔들 / 브로커 픽스처
# ---------------------------------------------------------------------------

_BUSINESS_DATE = "20260618"
_TODAY = date(2026, 6, 19)


def _make_candles(closes: list[int], volumes: list[int] | None = None) -> list[MinuteCandle]:
    if volumes is None:
        volumes = [1000] * len(closes)
    candles = []
    for i, (close, vol) in enumerate(zip(closes, volumes)):
        p = Decimal(close)
        candles.append(
            MinuteCandle(
                business_date=_BUSINESS_DATE,
                trade_time=f"{900 + i:04d}00",
                open_price=p,
                high_price=p,
                low_price=p,
                close_price=p,
                volume=vol,
            )
        )
    return candles


def _golden_cross_candles(volume_spike: bool = True) -> list[MinuteCandle]:
    """short=5, long=20 기준 골든크로스 + 거래량 스파이크 캔들 (21개)."""
    closes = [1000] * 20 + [2000]
    vols = [1000] * 20 + ([5000] if volume_spike else [500])
    return _make_candles(closes, vols)


class FakeBroker(BrokerClient):
    """분봉 데이터 픽스처용 브로커. place_order 호출 기록 포함."""

    def __init__(
        self,
        candles_by_symbol: dict[str, list[MinuteCandle]] | None = None,
    ) -> None:
        self._candles = candles_by_symbol or {}
        self.place_order_calls: list[OrderRequest] = []

    async def get_current_price(self, symbol_code: str) -> PriceQuote:  # type: ignore[override]
        raise NotImplementedError

    async def get_minute_candles(
        self, symbol_code: str, target_time: str | None = None, include_past_data: bool = True
    ) -> list[MinuteCandle]:
        return self._candles.get(symbol_code, [])

    async def get_account_balance(self) -> AccountBalance:
        return AccountBalance(
            holdings=[],
            summary=AccountSummary(
                total_deposit=Decimal("10000000"),
                total_purchase_amount=Decimal("0"),
                total_evaluation_amount=Decimal("0"),
                total_profit_loss_amount=Decimal("0"),
            ),
        )

    async def get_account_positions(self) -> list[AccountHolding]:
        return []

    async def place_order(self, order: OrderRequest) -> OrderResult:
        self.place_order_calls.append(order)
        return OrderResult(
            broker_order_id="0000000001",
            order_status=OrderStatus.PENDING,
        )

    async def get_daily_executions(self, *args, **kwargs) -> list[OrderExecution]:
        raise NotImplementedError


async def _add_strategy_version(
    session: AsyncSession,
    strategy_type: str = "moving_average_cross",
    symbol_code: str = "005930",
    account_id: int | None = None,
    status: StrategyVersionStatus = StrategyVersionStatus.TESTING,
    auto_trade_enabled: bool = False,
) -> StrategyVersion:
    strategy = Strategy(name=f"Test_{strategy_type}", description="test")
    session.add(strategy)
    await session.flush()

    params: dict = {
        "strategy_type": strategy_type,
        "symbol_code": symbol_code,
        "short_window": 5,
        "long_window": 20,
        "volume_window": 20,
        "volume_multiplier": 1.5,
        "quantity": 1,
        "timeframe": "5m",
        "enabled": True,
        "auto_trade_enabled": auto_trade_enabled,
    }
    if account_id is not None:
        params["account_id"] = account_id

    version = StrategyVersion(
        strategy_id=strategy.id,
        version_no=1,
        parameters=params,
        status=status,
    )
    session.add(version)
    await session.flush()
    return version


async def _create_paper_account(session: AsyncSession) -> Account:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000-01")
    session.add(account)
    await session.flush()
    return account


async def _create_risk_config(session: AsyncSession, account_id: int, **overrides) -> RiskConfig:
    defaults = dict(
        account_id=account_id,
        max_daily_loss_amount=Decimal("100000"),
        max_position_size=Decimal("1000000"),
        max_open_positions=5,
        max_trades_per_day=10,
        consecutive_loss_limit=3,
        emergency_stop=False,
    )
    defaults.update(overrides)
    rc = RiskConfig(**defaults)
    session.add(rc)
    await session.flush()
    return rc


# ---------------------------------------------------------------------------
# C-1. runner 인식 조건 (2)
# ---------------------------------------------------------------------------

async def test_list_active_includes_testing_status(db_session: AsyncSession) -> None:
    """status=TESTING인 strategy_version은 list_active()에 포함되어야 한다."""
    version = await _add_strategy_version(db_session, status=StrategyVersionStatus.TESTING)

    repo = StrategyVersionRepository(db_session)
    active = await repo.list_active()
    ids = [v.id for v in active]

    assert version.id in ids


async def test_list_active_excludes_draft_status(db_session: AsyncSession) -> None:
    """status=DRAFT인 strategy_version은 list_active()에 포함되어서는 안 된다."""
    version = await _add_strategy_version(db_session, status=StrategyVersionStatus.DRAFT)

    repo = StrategyVersionRepository(db_session)
    active = await repo.list_active()
    ids = [v.id for v in active]

    assert version.id not in ids


# ---------------------------------------------------------------------------
# B. 스크립트 동작 (3)
# ---------------------------------------------------------------------------

# 스크립트 import: _BACKEND_DIR을 sys.path에 추가해 직접 호출
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR.parent))


async def test_script_dry_run_no_db_change(db_session: AsyncSession) -> None:
    """dry-run 모드에서는 strategy_version이 생성/변경되지 않아야 한다."""
    from scripts.create_paper_strategy_versions import _run_activation

    account = await _create_paper_account(db_session)

    count_before = (
        await db_session.execute(select(func.count(StrategyVersion.id)))
    ).scalar()

    results = await _run_activation(db_session, account.id, "005930", apply=False)

    count_after = (
        await db_session.execute(select(func.count(StrategyVersion.id)))
    ).scalar()

    assert count_before == count_after, "dry-run인데 DB가 변경됐다"
    assert all(r.action == "dry_run" for r in results), "dry-run action이 아닌 결과 있음"
    assert len(results) == 2, "volume_confirmed + flow_confirmed 2건 결과"


async def test_script_apply_creates_versions_with_testing_status(db_session: AsyncSession) -> None:
    """--apply 모드에서 두 전략 버전이 status=TESTING, auto_trade_enabled=False로 생성된다."""
    from scripts.create_paper_strategy_versions import _run_activation

    account = await _create_paper_account(db_session)

    results = await _run_activation(db_session, account.id, "005930", apply=True)

    assert any(r.action == "created" and r.strategy_type == "volume_confirmed_ma_cross" for r in results)
    assert any(r.action == "created" and r.strategy_type == "flow_confirmed_volume_ma_cross" for r in results)

    versions_result = await db_session.execute(select(StrategyVersion))
    versions = list(versions_result.scalars().all())

    for v in versions:
        assert v.status == StrategyVersionStatus.TESTING, f"id={v.id}: status={v.status} (expected testing)"
        assert v.parameters.get("auto_trade_enabled") is False, "auto_trade_enabled must be False"
        assert v.parameters.get("account_id") == account.id, "account_id 불일치"
        assert v.parameters.get("symbol_code") == "005930"


async def test_script_apply_is_idempotent(db_session: AsyncSession) -> None:
    """--apply를 두 번 실행해도 strategy_version은 같은 수가 유지된다(중복 생성 없음)."""
    from scripts.create_paper_strategy_versions import _run_activation

    account = await _create_paper_account(db_session)

    await _run_activation(db_session, account.id, "005930", apply=True)
    count_after_first = (
        await db_session.execute(select(func.count(StrategyVersion.id)))
    ).scalar()

    results2 = await _run_activation(db_session, account.id, "005930", apply=True)
    count_after_second = (
        await db_session.execute(select(func.count(StrategyVersion.id)))
    ).scalar()

    assert count_after_first == count_after_second, "두 번째 실행에서 row가 추가됐다"
    assert all(r.action == "skipped_already_active" for r in results2), (
        "두 번째 실행은 모두 skipped여야 한다"
    )


# ---------------------------------------------------------------------------
# E-1. signal 생성 fixture-based (4)
# ---------------------------------------------------------------------------

async def test_volume_confirmed_buy_signal_generated(db_session: AsyncSession) -> None:
    """volume_confirmed_ma_cross 전략이 골든크로스+거래량 스파이크에서 BUY signal을 생성한다."""
    from app.domain.models.enums import TradeSide
    from app.trading.strategy.volume_confirmed_ma_cross import VolumeConfirmedMovingAverageCrossStrategy

    broker = FakeBroker({"005930": _golden_cross_candles(volume_spike=True)})
    service = SignalService(db_session, MarketDataService(broker))
    strategy = VolumeConfirmedMovingAverageCrossStrategy(
        short_window=5, long_window=20, volume_window=20, volume_multiplier=Decimal("1.5")
    )

    log = await service.generate_and_log_signal(strategy, "005930")

    assert log is not None, "BUY 시그널이 생성되어야 한다"
    assert log.signal_type == TradeSide.BUY


async def test_volume_confirmed_indicators_complete(db_session: AsyncSession) -> None:
    """volume_confirmed_ma_cross BUY signal의 indicators에 필수 키가 모두 포함된다."""
    from app.trading.strategy.volume_confirmed_ma_cross import VolumeConfirmedMovingAverageCrossStrategy

    broker = FakeBroker({"005930": _golden_cross_candles(volume_spike=True)})
    service = SignalService(db_session, MarketDataService(broker))
    strategy = VolumeConfirmedMovingAverageCrossStrategy()

    log = await service.generate_and_log_signal(strategy, "005930")

    assert log is not None
    indicators = log.indicators or {}
    required_keys = {"short_sma", "long_sma", "current_volume", "volume_sma", "volume_ratio", "volume_confirmed"}
    missing = required_keys - indicators.keys()
    assert not missing, f"indicators에 누락된 키: {missing}"
    assert indicators["volume_confirmed"] is True
    assert Decimal(str(indicators["volume_ratio"])) >= Decimal("1.5")


async def test_flow_confirmed_buy_signal_with_injected_context(db_session: AsyncSession) -> None:
    """flow_confirmed_volume_ma_cross 전략: investor_flow_repo 주입 + flow 데이터 있을 때 BUY 생성."""
    from app.domain.models.enums import TradeSide
    from app.trading.strategy.flow_confirmed_volume_ma_cross import FlowConfirmedVolumeMACrossStrategy

    candle_date = date(2026, 6, 18)
    flow_date = candle_date - timedelta(days=1)

    flow = InvestorFlow(
        symbol_code="005930",
        trade_date=flow_date,
        foreign_net_buy_quantity=1000,
        institution_net_buy_quantity=500,
        individual_net_buy_quantity=-1500,
        foreign_net_buy_amount=Decimal("5000"),
        institution_net_buy_amount=Decimal("2500"),
        individual_net_buy_amount=Decimal("-7500"),
    )
    db_session.add(flow)
    await db_session.flush()

    broker = FakeBroker({"005930": _golden_cross_candles(volume_spike=True)})
    flow_repo = InvestorFlowRepository(db_session)
    service = SignalService(db_session, MarketDataService(broker), investor_flow_repo=flow_repo)
    strategy = FlowConfirmedVolumeMACrossStrategy(
        short_window=5, long_window=20,
        volume_window=20, volume_multiplier=Decimal("1.5"),
        flow_mode="foreign_or_institution", require_flow_data=True,
    )

    strategy_params = {
        "strategy_type": "flow_confirmed_volume_ma_cross",
        "short_window": 5,
        "long_window": 20,
        "volume_window": 20,
        "volume_multiplier": 1.5,
        "flow_lookback_days": 5,
        "max_flow_age_days": 5,
        "flow_mode": "foreign_or_institution",
        "require_flow_data": True,
    }

    log = await service.generate_and_log_signal(strategy, "005930", strategy_params=strategy_params)

    assert log is not None, "flow 조건 충족 시 BUY 시그널이 생성되어야 한다"
    assert log.signal_type == TradeSide.BUY


async def test_flow_confirmed_all_indicators_in_jsonb(db_session: AsyncSession) -> None:
    """flow_confirmed 전략의 signal_log.indicators에 모든 수급 지표 키가 포함된다."""
    from app.trading.strategy.flow_confirmed_volume_ma_cross import FlowConfirmedVolumeMACrossStrategy

    candle_date = date(2026, 6, 18)
    flow_date = candle_date - timedelta(days=1)

    flow = InvestorFlow(
        symbol_code="005930",
        trade_date=flow_date,
        foreign_net_buy_quantity=2000,
        institution_net_buy_quantity=800,
        individual_net_buy_quantity=-2800,
        foreign_net_buy_amount=Decimal("10000"),
        institution_net_buy_amount=Decimal("4000"),
        individual_net_buy_amount=Decimal("-14000"),
    )
    db_session.add(flow)
    await db_session.flush()

    broker = FakeBroker({"005930": _golden_cross_candles(volume_spike=True)})
    flow_repo = InvestorFlowRepository(db_session)
    service = SignalService(db_session, MarketDataService(broker), investor_flow_repo=flow_repo)
    strategy = FlowConfirmedVolumeMACrossStrategy(
        volume_multiplier=Decimal("1.5"),
        flow_mode="foreign_or_institution",
        require_flow_data=True,
    )

    strategy_params = {
        "strategy_type": "flow_confirmed_volume_ma_cross",
        "flow_lookback_days": 5,
        "max_flow_age_days": 5,
        "flow_mode": "foreign_or_institution",
        "require_flow_data": True,
        "volume_multiplier": 1.5,
    }

    log = await service.generate_and_log_signal(strategy, "005930", strategy_params=strategy_params)

    assert log is not None, "BUY 시그널 없음 — 캔들/flow 조건 미충족"
    indicators = log.indicators or {}

    # MA / Volume 지표
    for key in ("short_sma", "long_sma", "current_volume", "volume_sma", "volume_ratio", "volume_confirmed"):
        assert key in indicators, f"누락: {key}"

    # Flow 지표
    flow_keys = [
        "flow_mode", "flow_data_available", "flow_confirmed",
        "flow_trade_date", "flow_data_staleness_days",
        "investor_foreign_net_buy_quantity",
        "investor_institution_net_buy_quantity",
        "investor_individual_net_buy_quantity",
        "investor_foreign_net_buy_amount",
        "investor_institution_net_buy_amount",
        "investor_individual_net_buy_amount",
        "investor_flow_amount_unit",
    ]
    for key in flow_keys:
        assert key in indicators, f"누락: {key}"

    assert indicators["flow_confirmed"] is True
    assert indicators["flow_data_available"] is True
    assert indicators["investor_flow_amount_unit"] == "million_krw"
    assert indicators["investor_foreign_net_buy_quantity"] == 2000
    assert indicators["investor_institution_net_buy_quantity"] == 800


# ---------------------------------------------------------------------------
# E-2. 실 DB 데이터 관찰 (1)
# ---------------------------------------------------------------------------

async def test_volume_confirmed_signal_on_seeded_market_data(db_session: AsyncSession) -> None:
    """시드 candle 데이터(DB에 저장)를 기반으로 volume_confirmed 전략 end-to-end 실행.

    market_data에 저장된 데이터로 signal_log까지 생성되어야 하며 예외 없이 완료되어야 한다.
    """
    from app.trading.strategy.volume_confirmed_ma_cross import VolumeConfirmedMovingAverageCrossStrategy

    candles = _golden_cross_candles(volume_spike=True)
    broker = FakeBroker({"005930": candles})
    svc = MarketDataService(broker, session=db_session)

    # 먼저 candles을 DB에 저장
    saved_count = await svc.save_candles("005930", "5m", candles)
    assert saved_count == len(candles)

    # 이제 Signal 생성 (broker에서 다시 읽지만 DB에도 저장됨)
    signal_svc = SignalService(db_session, MarketDataService(broker))
    strategy = VolumeConfirmedMovingAverageCrossStrategy(
        short_window=5, long_window=20,
        volume_window=20, volume_multiplier=Decimal("1.5"),
    )

    log = await signal_svc.generate_and_log_signal(strategy, "005930")

    # signal 생성 여부를 검증 (golden cross 조건을 충족하므로 BUY여야 함)
    assert log is not None, "DB 저장 후 signal_log가 생성되어야 한다"
    assert log.indicators is not None
    assert "volume_confirmed" in log.indicators


# ---------------------------------------------------------------------------
# F. 주문 미실행 (3)
# ---------------------------------------------------------------------------

async def test_auto_trade_disabled_trade_not_attempted(db_session: AsyncSession) -> None:
    """auto_trade_enabled=False이면 StrategyRunResult.trade_attempted == False이고
    broker.place_order가 호출되지 않는다."""
    account = await _create_paper_account(db_session)
    await _create_risk_config(db_session, account.id)

    candles = _golden_cross_candles(volume_spike=True)
    version = await _add_strategy_version(
        db_session,
        strategy_type="volume_confirmed_ma_cross",
        symbol_code="005930",
        account_id=account.id,
        status=StrategyVersionStatus.TESTING,
        auto_trade_enabled=False,
    )

    broker = FakeBroker({"005930": candles})
    risk_svc = RiskService(db_session, broker)
    trade_svc = TradeService(db_session, broker, risk_svc)
    runner = StrategyRunnerService(
        db_session,
        SignalService(db_session, MarketDataService(broker)),
        trade_svc,
    )

    results = await runner.run_once()

    assert results, "실행 결과가 없다"
    r = next((x for x in results if x.strategy_version_id == version.id), None)
    assert r is not None
    assert r.trade_attempted is False, "auto_trade_enabled=False인데 주문 시도됨"
    assert not broker.place_order_calls, "broker.place_order가 호출됐다"


async def test_place_order_not_called_when_auto_trade_disabled(db_session: AsyncSession) -> None:
    """auto_trade_enabled=False일 때 broker.place_order는 절대 호출되지 않아야 한다.
    BUY signal이 생성되어도 마찬가지다."""
    from unittest.mock import AsyncMock

    account = await _create_paper_account(db_session)
    await _create_risk_config(db_session, account.id)

    await _add_strategy_version(
        db_session,
        strategy_type="volume_confirmed_ma_cross",
        symbol_code="005930",
        account_id=account.id,
        status=StrategyVersionStatus.TESTING,
        auto_trade_enabled=False,
    )

    broker = FakeBroker({"005930": _golden_cross_candles(volume_spike=True)})
    broker.place_order = AsyncMock()  # type: ignore[method-assign]

    runner = StrategyRunnerService(
        db_session,
        SignalService(db_session, MarketDataService(broker)),
    )

    await runner.run_once()

    broker.place_order.assert_not_called()


async def test_guard_paused_auto_trade_skipped(db_session: AsyncSession) -> None:
    """TradingGuardState.is_paused=True이면 auto_trade_enabled=True여도 주문이 시도되지 않는다."""
    account = await _create_paper_account(db_session)
    await _create_risk_config(db_session, account.id)

    # TradingGuardState 생성 (is_paused=True)
    guard = TradingGuardState(
        account_id=account.id,
        is_paused=True,
        pause_source=PauseSource.MANUAL,
        pause_reason="테스트 강제 pause",
    )
    db_session.add(guard)
    await db_session.flush()

    candles = _golden_cross_candles(volume_spike=True)
    await _add_strategy_version(
        db_session,
        strategy_type="volume_confirmed_ma_cross",
        symbol_code="005930",
        account_id=account.id,
        status=StrategyVersionStatus.TESTING,
        auto_trade_enabled=True,
    )

    broker = FakeBroker({"005930": candles})
    risk_svc = RiskService(db_session, broker)
    trade_svc = TradeService(db_session, broker, risk_svc)
    runner = StrategyRunnerService(
        db_session,
        SignalService(db_session, MarketDataService(broker)),
        trade_svc,
    )

    results = await runner.run_once()

    assert results
    r = results[0]
    assert r.trade_attempted is False, "guard pause 상태인데 주문 시도됨"
    assert not broker.place_order_calls, "broker.place_order가 호출됐다"
