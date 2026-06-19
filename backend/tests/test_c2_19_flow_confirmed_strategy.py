"""C-2.19 Flow Confirmed Volume MA Cross Strategy 테스트.

테스트 범위:
1. StrategyContext 전달 구조
2. 기존 전략 회귀 (moving_average_cross, volume_confirmed_ma_cross)
3. flow_confirmed_volume_ma_cross registry 등록
4~6. flow_mode별 BUY 조건
7. smart_money_vs_retail BUY
8. require_flow_data=true + 데이터 없음 → BUY 방지
9. require_flow_data=false + 데이터 없음 → volume+MA 동치 동작
10. stale flow + require_flow_data=true → BUY 방지
11. look-ahead 방지: 캔들 당일 데이터 미사용
12. flow_mode invalid → validation error
13. StrategyVersionParameters flow_* validation
14. signal indicators에 flow metadata 저장
15. amount unit(million_krw) metadata 포함
16. strategy/runner에서 KISInvestorFlowClient 미호출 확인
17. broker.place_order 미호출 확인
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import TradeSide
from app.domain.models.investor_flow import InvestorFlow
from app.domain.repositories.investor_flow import InvestorFlowRepository
from app.services.market_data_service import MarketDataService
from app.services.signal_service import SignalService
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
from app.trading.strategy.base import Strategy
from app.trading.strategy.context import StrategyContext
from app.trading.strategy.flow_confirmed_volume_ma_cross import (
    FlowConfirmedVolumeMACrossStrategy,
    _check_flow_condition,
)
from app.trading.strategy.moving_average_cross import MovingAverageCrossStrategy
from app.trading.strategy.registry import create_strategy, registered_types
from app.trading.strategy.schemas import StrategyVersionParameters
from app.trading.strategy.volume_confirmed_ma_cross import VolumeConfirmedMovingAverageCrossStrategy

# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------

TODAY = date(2026, 6, 19)
YESTERDAY = TODAY - timedelta(days=1)
TWO_DAYS_AGO = TODAY - timedelta(days=2)


def _make_candles(
    closes: list[int | float],
    volumes: list[int] | None = None,
    business_date: str = "20260619",
) -> list[MinuteCandle]:
    if volumes is None:
        volumes = [1000] * len(closes)
    return [
        MinuteCandle(
            business_date=business_date,
            trade_time=f"{900 + i:04d}00",
            open_price=Decimal(str(c)),
            high_price=Decimal(str(c)),
            low_price=Decimal(str(c)),
            close_price=Decimal(str(c)),
            volume=v,
        )
        for i, (c, v) in enumerate(zip(closes, volumes))
    ]


def _golden_cross_candles(volume_spike: bool = True, business_date: str = "20260619") -> list[MinuteCandle]:
    """short=5, long=20 기준 골든크로스 + 거래량 spike 데이터."""
    closes = [100] * 20 + [200]
    volumes = [1000] * 20 + [2000 if volume_spike else 500]
    return _make_candles(closes, volumes, business_date=business_date)


def _dead_cross_candles(business_date: str = "20260619") -> list[MinuteCandle]:
    closes = [100] * 20 + [0]
    return _make_candles(closes, business_date=business_date)


def _make_flow(
    trade_date: date = YESTERDAY,
    foreign_qty: int = 100,
    institution_qty: int = 50,
    individual_qty: int = -80,
    foreign_amount: Decimal | None = None,
    institution_amount: Decimal | None = None,
    individual_amount: Decimal | None = None,
) -> InvestorFlow:
    flow = InvestorFlow()
    flow.symbol_code = "005930"
    flow.trade_date = trade_date
    flow.foreign_net_buy_quantity = foreign_qty
    flow.institution_net_buy_quantity = institution_qty
    flow.individual_net_buy_quantity = individual_qty
    flow.foreign_net_buy_amount = foreign_amount or Decimal("1000.0")
    flow.institution_net_buy_amount = institution_amount or Decimal("500.0")
    flow.individual_net_buy_amount = individual_amount or Decimal("-800.0")
    flow.source = "kis"
    return flow


class FakeBrokerClient(BrokerClient):
    """테스트용 브로커 클라이언트 — place_order 호출 시 AssertionError."""

    def __init__(self, candles: list[MinuteCandle]) -> None:
        self._candles = candles
        self.place_order_called = False

    async def get_current_price(self, symbol_code: str) -> PriceQuote:
        raise NotImplementedError

    async def get_minute_candles(
        self, symbol_code: str, target_time: str | None = None, include_past_data: bool = True
    ) -> list[MinuteCandle]:
        return self._candles

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
        self.place_order_called = True
        raise AssertionError("place_order must NOT be called in C-2.19 tests")

    async def get_daily_executions(self, target_date: str | None = None) -> list[OrderExecution]:
        raise NotImplementedError


def _make_context(
    flow: InvestorFlow | None = None,
    staleness_days: int = 1,
    available: bool = True,
) -> StrategyContext:
    return StrategyContext(
        latest_investor_flow=flow,
        investor_flows=[flow] if flow else [],
        flow_data_available=available and flow is not None,
        flow_data_date=flow.trade_date if flow else None,
        flow_data_staleness_days=staleness_days if flow else None,
    )


# ---------------------------------------------------------------------------
# 테스트 1: StrategyContext 전달 구조 — context가 generate_signal까지 도달
# ---------------------------------------------------------------------------


def test_context_reaches_generate_signal() -> None:
    """FlowConfirmedVolumeMACrossStrategy.generate_signal에 context가 전달된다."""
    received_ctx: list[StrategyContext | None] = []

    class ContextCapture(FlowConfirmedVolumeMACrossStrategy):
        def generate_signal(self, symbol_code, candles, strategy_version_id=None, context=None):
            received_ctx.append(context)
            return super().generate_signal(symbol_code, candles, strategy_version_id, context)

    strategy = ContextCapture(require_flow_data=False)
    flow = _make_flow()
    ctx = _make_context(flow=flow)
    candles = _golden_cross_candles()
    strategy.generate_signal("005930", candles, 1, context=ctx)

    assert len(received_ctx) == 1
    assert received_ctx[0] is ctx


# ---------------------------------------------------------------------------
# 테스트 2~3: 기존 전략 회귀 (기존 테스트와 독립적 확인)
# ---------------------------------------------------------------------------


def test_existing_ma_cross_unaffected_by_context() -> None:
    """MovingAverageCrossStrategy는 context를 무시하고 기존 동작을 유지한다."""
    strategy = MovingAverageCrossStrategy(short_window=5, long_window=20)
    candles = _golden_cross_candles()
    signal = strategy.generate_signal("005930", candles, context=_make_context(_make_flow()))
    assert signal is not None
    assert signal.side == TradeSide.BUY


def test_existing_volume_confirmed_unaffected_by_context() -> None:
    """VolumeConfirmedMovingAverageCrossStrategy는 context를 무시하고 기존 동작을 유지한다."""
    strategy = VolumeConfirmedMovingAverageCrossStrategy(
        short_window=5, long_window=20, volume_window=20, volume_multiplier=Decimal("1.5")
    )
    candles = _golden_cross_candles(volume_spike=True)
    signal = strategy.generate_signal("005930", candles, context=None)
    assert signal is not None
    assert signal.side == TradeSide.BUY


# ---------------------------------------------------------------------------
# 테스트 4: flow_confirmed_volume_ma_cross registry 등록
# ---------------------------------------------------------------------------


def test_flow_confirmed_strategy_is_registered() -> None:
    assert "flow_confirmed_volume_ma_cross" in registered_types()
    strategy = create_strategy("flow_confirmed_volume_ma_cross", {
        "symbol_code": "005930",
        "short_window": 5,
        "long_window": 20,
        "volume_window": 20,
        "volume_multiplier": 1.5,
        "flow_lookback_days": 5,
        "max_flow_age_days": 5,
        "flow_mode": "foreign_or_institution",
        "require_flow_data": True,
    })
    assert strategy is not None
    assert isinstance(strategy, FlowConfirmedVolumeMACrossStrategy)


# ---------------------------------------------------------------------------
# 테스트 5: MA + volume + 외국인 순매수 → BUY (foreign_or_institution)
# ---------------------------------------------------------------------------


def test_buy_foreign_net_buy_foreign_or_institution() -> None:
    strategy = FlowConfirmedVolumeMACrossStrategy(
        short_window=5, long_window=20, volume_window=20,
        volume_multiplier=Decimal("1.5"), flow_mode="foreign_or_institution",
    )
    flow = _make_flow(foreign_qty=100, institution_qty=-50)  # 외국인 순매수만
    ctx = _make_context(flow=flow)
    signal = strategy.generate_signal("005930", _golden_cross_candles(), context=ctx)
    assert signal is not None
    assert signal.side == TradeSide.BUY


# ---------------------------------------------------------------------------
# 테스트 6: MA + volume + 기관 순매수 → BUY (foreign_or_institution)
# ---------------------------------------------------------------------------


def test_buy_institution_net_buy_foreign_or_institution() -> None:
    strategy = FlowConfirmedVolumeMACrossStrategy(
        short_window=5, long_window=20, volume_window=20,
        volume_multiplier=Decimal("1.5"), flow_mode="foreign_or_institution",
    )
    flow = _make_flow(foreign_qty=-100, institution_qty=200)  # 기관 순매수만
    ctx = _make_context(flow=flow)
    signal = strategy.generate_signal("005930", _golden_cross_candles(), context=ctx)
    assert signal is not None
    assert signal.side == TradeSide.BUY


# ---------------------------------------------------------------------------
# 테스트 7: smart_money_vs_retail 조건 충족 → BUY
# ---------------------------------------------------------------------------


def test_buy_smart_money_vs_retail() -> None:
    strategy = FlowConfirmedVolumeMACrossStrategy(
        short_window=5, long_window=20, volume_window=20,
        volume_multiplier=Decimal("1.5"), flow_mode="smart_money_vs_retail",
    )
    # 외국인+기관 순매수, 개인 순매도
    flow = _make_flow(foreign_qty=100, institution_qty=50, individual_qty=-200)
    ctx = _make_context(flow=flow)
    signal = strategy.generate_signal("005930", _golden_cross_candles(), context=ctx)
    assert signal is not None
    assert signal.side == TradeSide.BUY


def test_no_buy_smart_money_vs_retail_when_individual_positive() -> None:
    """smart_money_vs_retail: 개인도 순매수이면 조건 미충족."""
    strategy = FlowConfirmedVolumeMACrossStrategy(
        short_window=5, long_window=20, volume_window=20,
        volume_multiplier=Decimal("1.5"), flow_mode="smart_money_vs_retail",
    )
    flow = _make_flow(foreign_qty=100, institution_qty=50, individual_qty=100)  # 개인도 순매수
    ctx = _make_context(flow=flow)
    signal = strategy.generate_signal("005930", _golden_cross_candles(), context=ctx)
    assert signal is None


# ---------------------------------------------------------------------------
# 테스트 8: 데이터 없음 + require_flow_data=true → BUY 방지
# ---------------------------------------------------------------------------


def test_no_buy_when_no_flow_data_and_required() -> None:
    strategy = FlowConfirmedVolumeMACrossStrategy(
        short_window=5, long_window=20, volume_window=20,
        volume_multiplier=Decimal("1.5"), require_flow_data=True,
    )
    ctx = StrategyContext(flow_data_available=False)
    signal = strategy.generate_signal("005930", _golden_cross_candles(), context=ctx)
    assert signal is None


def test_no_buy_when_context_none_and_required() -> None:
    strategy = FlowConfirmedVolumeMACrossStrategy(
        short_window=5, long_window=20, volume_window=20,
        volume_multiplier=Decimal("1.5"), require_flow_data=True,
    )
    signal = strategy.generate_signal("005930", _golden_cross_candles(), context=None)
    assert signal is None


# ---------------------------------------------------------------------------
# 테스트 9: 데이터 없음 + require_flow_data=false → volume_confirmed_ma_cross 동치
# ---------------------------------------------------------------------------


def test_buy_when_no_flow_data_and_not_required() -> None:
    """require_flow_data=false이면 수급 없이도 MA+volume 조건만으로 BUY."""
    strategy = FlowConfirmedVolumeMACrossStrategy(
        short_window=5, long_window=20, volume_window=20,
        volume_multiplier=Decimal("1.5"), require_flow_data=False,
    )
    ctx = StrategyContext(flow_data_available=False)
    signal = strategy.generate_signal("005930", _golden_cross_candles(volume_spike=True), context=ctx)
    assert signal is not None
    assert signal.side == TradeSide.BUY

    # volume 부족이면 여전히 None
    signal_no_vol = strategy.generate_signal(
        "005930", _golden_cross_candles(volume_spike=False), context=ctx
    )
    assert signal_no_vol is None


def test_flow_data_available_false_recorded_in_metadata_when_not_required() -> None:
    strategy = FlowConfirmedVolumeMACrossStrategy(
        short_window=5, long_window=20, volume_window=20,
        volume_multiplier=Decimal("1.5"), require_flow_data=False,
    )
    ctx = StrategyContext(flow_data_available=False)
    signal = strategy.generate_signal("005930", _golden_cross_candles(), context=ctx)
    assert signal is not None
    meta = signal.metadata or {}
    assert meta.get("flow_data_available") is False


# ---------------------------------------------------------------------------
# 테스트 10: stale flow + require_flow_data=true → BUY 방지
# ---------------------------------------------------------------------------


def test_no_buy_when_stale_flow_and_required() -> None:
    strategy = FlowConfirmedVolumeMACrossStrategy(
        short_window=5, long_window=20, volume_window=20,
        volume_multiplier=Decimal("1.5"),
        max_flow_age_days=3, require_flow_data=True,
    )
    old_flow = _make_flow(trade_date=TODAY - timedelta(days=10))  # 10일 전 = stale
    ctx = StrategyContext(
        latest_investor_flow=old_flow,
        investor_flows=[old_flow],
        flow_data_available=False,  # SignalService가 staleness 체크 후 False로 설정
        flow_data_date=old_flow.trade_date,
        flow_data_staleness_days=10,
    )
    signal = strategy.generate_signal("005930", _golden_cross_candles(), context=ctx)
    assert signal is None


def test_buy_when_stale_flow_and_not_required() -> None:
    strategy = FlowConfirmedVolumeMACrossStrategy(
        short_window=5, long_window=20, volume_window=20,
        volume_multiplier=Decimal("1.5"),
        max_flow_age_days=3, require_flow_data=False,
    )
    old_flow = _make_flow(trade_date=TODAY - timedelta(days=10))
    ctx = StrategyContext(
        latest_investor_flow=old_flow,
        flow_data_available=False,  # stale → False
        flow_data_date=old_flow.trade_date,
        flow_data_staleness_days=10,
    )
    signal = strategy.generate_signal("005930", _golden_cross_candles(), context=ctx)
    assert signal is not None
    assert signal.side == TradeSide.BUY


# ---------------------------------------------------------------------------
# 테스트 11: look-ahead 방지 — SignalService가 캔들 당일 데이터를 context에서 제외
# ---------------------------------------------------------------------------


async def test_look_ahead_prevention_in_signal_service(db_session: AsyncSession) -> None:
    """SignalService._build_strategy_context가 캔들 business_date 당일 flow를 제외한다."""
    # DB에 오늘(20260619) trade_date flow 삽입 — look-ahead 데이터
    today_flow = InvestorFlow()
    today_flow.symbol_code = "005930"
    today_flow.trade_date = TODAY  # 캔들 당일 → 사용 금지
    today_flow.foreign_net_buy_quantity = 999
    today_flow.institution_net_buy_quantity = 999
    today_flow.individual_net_buy_quantity = -999
    today_flow.foreign_net_buy_amount = Decimal("9999")
    today_flow.institution_net_buy_amount = Decimal("9999")
    today_flow.individual_net_buy_amount = Decimal("-9999")
    today_flow.source = "kis"
    db_session.add(today_flow)
    await db_session.flush()

    repo = InvestorFlowRepository(db_session)
    candles = _golden_cross_candles(business_date="20260619")  # 오늘 캔들

    broker = FakeBrokerClient(candles)
    service = SignalService(db_session, MarketDataService(broker, db_session), repo)
    context = await service._build_strategy_context("005930", candles, {
        "flow_lookback_days": 5,
        "max_flow_age_days": 5,
    })

    # 오늘(20260619) 데이터는 제외돼야 한다 — date_to = 20260618
    assert context.latest_investor_flow is None or context.latest_investor_flow.trade_date < TODAY


async def test_look_ahead_yesterday_flow_is_included(db_session: AsyncSession) -> None:
    """캔들 전날(20260618) flow는 context에 포함된다."""
    yesterday_flow = InvestorFlow()
    yesterday_flow.symbol_code = "005930"
    yesterday_flow.trade_date = YESTERDAY
    yesterday_flow.foreign_net_buy_quantity = 100
    yesterday_flow.institution_net_buy_quantity = 50
    yesterday_flow.individual_net_buy_quantity = -80
    yesterday_flow.foreign_net_buy_amount = Decimal("1000")
    yesterday_flow.institution_net_buy_amount = Decimal("500")
    yesterday_flow.individual_net_buy_amount = Decimal("-800")
    yesterday_flow.source = "kis"
    db_session.add(yesterday_flow)
    await db_session.flush()

    repo = InvestorFlowRepository(db_session)
    candles = _golden_cross_candles(business_date="20260619")
    broker = FakeBrokerClient(candles)
    service = SignalService(db_session, MarketDataService(broker, db_session), repo)
    context = await service._build_strategy_context("005930", candles, {
        "flow_lookback_days": 5,
        "max_flow_age_days": 5,
    })

    assert context.latest_investor_flow is not None
    assert context.latest_investor_flow.trade_date == YESTERDAY
    assert context.flow_data_available is True


# ---------------------------------------------------------------------------
# 테스트 12: flow_mode invalid → validation error
# ---------------------------------------------------------------------------


def test_invalid_flow_mode_raises_validation_error() -> None:
    import pytest
    with pytest.raises(Exception):
        StrategyVersionParameters(
            symbol_code="005930",
            strategy_type="flow_confirmed_volume_ma_cross",
            flow_mode="invalid_mode",
        )


# ---------------------------------------------------------------------------
# 테스트 13: StrategyVersionParameters flow_* validation
# ---------------------------------------------------------------------------


def test_flow_params_validation_ok() -> None:
    p = StrategyVersionParameters(
        symbol_code="005930",
        strategy_type="flow_confirmed_volume_ma_cross",
        flow_lookback_days=5,
        max_flow_age_days=5,
        flow_mode="foreign_or_institution",
        require_flow_data=True,
    )
    assert p.flow_lookback_days == 5
    assert p.max_flow_age_days == 5
    assert p.flow_mode == "foreign_or_institution"
    assert p.require_flow_data is True


def test_flow_params_validation_all_modes() -> None:
    for mode in ("foreign_or_institution", "foreign_and_institution", "smart_money_vs_retail"):
        p = StrategyVersionParameters(
            symbol_code="005930",
            strategy_type="flow_confirmed_volume_ma_cross",
            flow_mode=mode,
        )
        assert p.flow_mode == mode


def test_flow_params_lookback_days_gt0() -> None:
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        StrategyVersionParameters(
            symbol_code="005930",
            strategy_type="flow_confirmed_volume_ma_cross",
            flow_lookback_days=0,
        )


# ---------------------------------------------------------------------------
# 테스트 14~15: signal indicators에 flow metadata + amount_unit 저장
# ---------------------------------------------------------------------------


async def test_flow_metadata_saved_in_indicators(db_session: AsyncSession) -> None:
    """flow_confirmed_volume_ma_cross BUY 신호 시 indicators에 flow 메타데이터가 포함된다."""
    flow = _make_flow(
        trade_date=YESTERDAY,
        foreign_qty=100,
        institution_qty=50,
        individual_qty=-80,
        foreign_amount=Decimal("1000.0"),
        institution_amount=Decimal("500.0"),
        individual_amount=Decimal("-800.0"),
    )
    db_session.add(flow)
    await db_session.flush()

    candles = _golden_cross_candles(business_date="20260619")
    broker = FakeBrokerClient(candles)
    repo = InvestorFlowRepository(db_session)
    service = SignalService(db_session, MarketDataService(broker, db_session), repo)
    strategy = FlowConfirmedVolumeMACrossStrategy(
        short_window=5, long_window=20, volume_window=20,
        volume_multiplier=Decimal("1.5"),
        flow_lookback_days=5, max_flow_age_days=5,
        flow_mode="foreign_or_institution",
    )
    params = {
        "strategy_type": "flow_confirmed_volume_ma_cross",
        "flow_lookback_days": 5,
        "max_flow_age_days": 5,
        "flow_mode": "foreign_or_institution",
        "require_flow_data": True,
    }
    log = await service.generate_and_log_signal(strategy, "005930", None, strategy_params=params)

    assert log is not None
    assert log.signal_type == TradeSide.BUY
    ind = log.indicators or {}
    assert "flow_confirmed" in ind
    assert ind["flow_confirmed"] is True
    assert "flow_mode" in ind
    assert ind["flow_mode"] == "foreign_or_institution"
    assert "flow_trade_date" in ind
    assert ind["flow_trade_date"] == YESTERDAY.isoformat()
    assert "investor_foreign_net_buy_quantity" in ind
    assert ind["investor_foreign_net_buy_quantity"] == 100
    assert "investor_institution_net_buy_quantity" in ind
    assert "investor_individual_net_buy_quantity" in ind


async def test_amount_unit_million_krw_in_indicators(db_session: AsyncSession) -> None:
    """indicators에 investor_flow_amount_unit='million_krw' 가 포함된다."""
    flow = _make_flow(trade_date=YESTERDAY)
    db_session.add(flow)
    await db_session.flush()

    candles = _golden_cross_candles(business_date="20260619")
    broker = FakeBrokerClient(candles)
    repo = InvestorFlowRepository(db_session)
    service = SignalService(db_session, MarketDataService(broker, db_session), repo)
    strategy = FlowConfirmedVolumeMACrossStrategy(
        short_window=5, long_window=20, volume_window=20,
        volume_multiplier=Decimal("1.5"), flow_mode="foreign_or_institution",
    )
    params = {"flow_lookback_days": 5, "max_flow_age_days": 5}
    log = await service.generate_and_log_signal(strategy, "005930", None, strategy_params=params)

    assert log is not None
    ind = log.indicators or {}
    assert ind.get("investor_flow_amount_unit") == "million_krw"


# ---------------------------------------------------------------------------
# 테스트 16: runner/전략이 KISInvestorFlowClient 직접 호출 금지
# ---------------------------------------------------------------------------


def test_strategy_does_not_import_kis_investor_flow_client() -> None:
    """FlowConfirmedVolumeMACrossStrategy 모듈에 KISInvestorFlowClient import 없음."""
    import ast
    import inspect
    import app.trading.strategy.flow_confirmed_volume_ma_cross as module

    source = inspect.getsource(module)
    assert "KISInvestorFlowClient" not in source, (
        "전략 모듈이 KISInvestorFlowClient를 직접 import/참조하면 안 됩니다"
    )


def test_strategy_does_not_call_investor_flow_service() -> None:
    """FlowConfirmedVolumeMACrossStrategy 모듈에 InvestorFlowService 참조 없음."""
    import inspect
    import app.trading.strategy.flow_confirmed_volume_ma_cross as module

    source = inspect.getsource(module)
    assert "InvestorFlowService" not in source


# ---------------------------------------------------------------------------
# 테스트 17: broker.place_order 미호출
# ---------------------------------------------------------------------------


async def test_broker_place_order_not_called(db_session: AsyncSession) -> None:
    """SignalService.generate_and_log_signal은 broker.place_order를 호출하지 않는다."""
    flow = _make_flow(trade_date=YESTERDAY)
    db_session.add(flow)
    await db_session.flush()

    candles = _golden_cross_candles(business_date="20260619")
    broker = FakeBrokerClient(candles)
    repo = InvestorFlowRepository(db_session)
    service = SignalService(db_session, MarketDataService(broker, db_session), repo)
    strategy = FlowConfirmedVolumeMACrossStrategy(
        short_window=5, long_window=20, volume_window=20,
        volume_multiplier=Decimal("1.5"), flow_mode="foreign_or_institution",
    )
    params = {"flow_lookback_days": 5, "max_flow_age_days": 5}
    await service.generate_and_log_signal(strategy, "005930", None, strategy_params=params)

    assert not broker.place_order_called, "place_order가 호출되면 안 됩니다"


# ---------------------------------------------------------------------------
# _check_flow_condition 단위 테스트
# ---------------------------------------------------------------------------


def test_check_flow_condition_foreign_or_institution() -> None:
    flow_all_positive = _make_flow(foreign_qty=1, institution_qty=1, individual_qty=-1)
    assert _check_flow_condition(flow_all_positive, "foreign_or_institution") is True

    flow_only_foreign = _make_flow(foreign_qty=1, institution_qty=-1)
    assert _check_flow_condition(flow_only_foreign, "foreign_or_institution") is True

    flow_only_inst = _make_flow(foreign_qty=-1, institution_qty=1)
    assert _check_flow_condition(flow_only_inst, "foreign_or_institution") is True

    flow_both_negative = _make_flow(foreign_qty=-1, institution_qty=-1)
    assert _check_flow_condition(flow_both_negative, "foreign_or_institution") is False


def test_check_flow_condition_foreign_and_institution() -> None:
    flow_both = _make_flow(foreign_qty=1, institution_qty=1)
    assert _check_flow_condition(flow_both, "foreign_and_institution") is True

    flow_only_foreign = _make_flow(foreign_qty=1, institution_qty=-1)
    assert _check_flow_condition(flow_only_foreign, "foreign_and_institution") is False


def test_check_flow_condition_smart_money_vs_retail() -> None:
    flow_smart_win = _make_flow(foreign_qty=1, institution_qty=0, individual_qty=-1)
    assert _check_flow_condition(flow_smart_win, "smart_money_vs_retail") is True

    flow_all_buy = _make_flow(foreign_qty=1, institution_qty=1, individual_qty=1)
    assert _check_flow_condition(flow_all_buy, "smart_money_vs_retail") is False

    flow_only_retail = _make_flow(foreign_qty=-1, institution_qty=-1, individual_qty=1)
    assert _check_flow_condition(flow_only_retail, "smart_money_vs_retail") is False


# ---------------------------------------------------------------------------
# SELL 신호는 flow 무관하게 발생
# ---------------------------------------------------------------------------


def test_sell_signal_ignores_flow() -> None:
    """SELL(데드크로스)은 수급 조건 없이 발생한다."""
    strategy = FlowConfirmedVolumeMACrossStrategy(
        short_window=5, long_window=20, volume_window=20,
        volume_multiplier=Decimal("1.5"), require_flow_data=True,
    )
    # flow 없음 (require_flow_data=True) — 그래도 SELL은 발생해야 한다
    signal = strategy.generate_signal("005930", _dead_cross_candles(), context=None)
    assert signal is not None
    assert signal.side == TradeSide.SELL


# ---------------------------------------------------------------------------
# foreign_and_institution 모드 — 둘 다 필요
# ---------------------------------------------------------------------------


def test_no_buy_when_institution_negative_and_foreign_and_institution() -> None:
    strategy = FlowConfirmedVolumeMACrossStrategy(
        short_window=5, long_window=20, volume_window=20,
        volume_multiplier=Decimal("1.5"), flow_mode="foreign_and_institution",
    )
    flow = _make_flow(foreign_qty=100, institution_qty=-50)  # 기관 순매도
    ctx = _make_context(flow=flow)
    signal = strategy.generate_signal("005930", _golden_cross_candles(), context=ctx)
    assert signal is None
