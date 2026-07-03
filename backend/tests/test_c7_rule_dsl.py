"""C-7.1: 전략 DSL — 검증기·평가기·rule_based 전략·백테스트 통합.

안전 검증: 알 수 없는 fn/op/참조는 통과 불가(임의 코드 실행 차단),
데이터 부족 시 신호 없음, 기존 파이프라인(registry/백테스트)과 즉시 호환.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pydantic
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import TradeSide
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.registry import create_strategy, registered_types
from app.trading.strategy.rule_dsl import (
    RuleEvaluator,
    RuleSpecError,
    required_bars,
    validate_rule_spec,
)
from app.trading.strategy.schemas import StrategyVersionParameters


def _c(i: int, close: int, high: int | None = None, low: int | None = None, vol: int = 1000):
    return MinuteCandle(
        business_date="20260706", trade_time=f"{9 + i // 60:02d}{i % 60:02d}00",
        open_price=Decimal(close), high_price=Decimal(high or close),
        low_price=Decimal(low or close), close_price=Decimal(close), volume=vol,
    )


BOLLINGER_SPEC = {
    "name": "bollinger_bounce",
    "source": "볼린저 밴드 평균회귀",
    "indicators": {
        "bb_lower": {"fn": "bollinger_lower", "period": 5, "num_std": 1.0},
        "bb_mid": {"fn": "bollinger_mid", "period": 5},
    },
    "entry": {"op": "lt", "left": {"ref": "price"}, "right": {"ref": "bb_lower"}},
    "exit": {"op": "crosses_above", "left": {"ref": "price"}, "right": {"ref": "bb_mid"}},
}


# ── 검증기 ──────────────────────────────────────────────────────────────


def test_validate_accepts_wellformed_spec():
    validate_rule_spec(BOLLINGER_SPEC)  # no raise
    assert required_bars(BOLLINGER_SPEC) >= 6


@pytest.mark.parametrize(
    "mutate,msg",
    [
        (lambda s: s.update(indicators={"x": {"fn": "eval_python", "period": 5}}), "알 수 없는 fn"),
        (lambda s: s.update(entry={"op": "exec", "left": {"const": 1}, "right": {"const": 2}}), "알 수 없는 op"),
        (lambda s: s.update(entry={"op": "gt", "left": {"ref": "없는지표"}, "right": {"const": 1}}), "정의되지 않은 참조"),
        (lambda s: s.update(exit=None), "조건이 필요"),
        (lambda s: s["indicators"].update(bad={"fn": "sma", "period": 99999}), "숫자여야"),
    ],
)
def test_validate_rejects_malformed(mutate, msg):
    spec = {
        "name": "t", "indicators": dict(BOLLINGER_SPEC["indicators"]),
        "entry": dict(BOLLINGER_SPEC["entry"]), "exit": dict(BOLLINGER_SPEC["exit"]),
    }
    mutate(spec)
    with pytest.raises(RuleSpecError, match=msg):
        validate_rule_spec(spec)


def test_validate_rejects_deep_nesting():
    node = {"op": "gt", "left": {"const": 1}, "right": {"const": 0}}
    for _ in range(8):
        node = {"op": "and", "args": [node]}
    with pytest.raises(RuleSpecError, match="중첩"):
        validate_rule_spec({"name": "t", "indicators": {}, "entry": node, "exit": node})


# ── 평가기 ──────────────────────────────────────────────────────────────


def test_evaluator_compare_and_logic():
    spec = {
        "name": "t", "indicators": {"s3": {"fn": "sma", "period": 3}},
        "entry": {"op": "and", "args": [
            {"op": "gt", "left": {"ref": "price"}, "right": {"ref": "s3"}},
            {"op": "not", "args": [{"op": "lt", "left": {"ref": "volume"}, "right": {"const": 10}}]},
        ]},
        "exit": {"op": "lt", "left": {"ref": "price"}, "right": {"ref": "s3"}},
    }
    validate_rule_spec(spec)
    ev = RuleEvaluator(spec)
    candles = [_c(0, 100), _c(1, 100), _c(2, 100), _c(3, 120)]  # price 120 > sma3
    assert ev.entry(candles) is True
    assert ev.exit(candles) is False


def test_evaluator_crosses_above():
    spec = {
        "name": "t", "indicators": {"s3": {"fn": "sma", "period": 3}},
        "entry": {"op": "crosses_above", "left": {"ref": "price"}, "right": {"ref": "s3"}},
        "exit": {"op": "crosses_below", "left": {"ref": "price"}, "right": {"ref": "s3"}},
    }
    ev = RuleEvaluator(spec)
    # 직전: price(90) <= sma, 현재: price(130) > sma → 상향 교차
    crossing = [_c(0, 100), _c(1, 100), _c(2, 100), _c(3, 90), _c(4, 130)]
    assert ev.entry(crossing) is True
    # 이미 위에 있던 경우(교차 아님)
    stayed = [_c(0, 100), _c(1, 100), _c(2, 120), _c(3, 125), _c(4, 130)]
    assert ev.entry(stayed) is False


def test_evaluator_insufficient_data_is_false():
    ev = RuleEvaluator(BOLLINGER_SPEC)
    assert ev.entry([_c(0, 100)]) is False  # 지표 None → False (신호 없음)


# ── rule_based 전략 (registry 경유) ─────────────────────────────────────


def test_rule_based_registered_and_generates_signals():
    assert "rule_based" in registered_types()
    strategy = create_strategy(
        "rule_based", {"rule_spec": BOLLINGER_SPEC, "quantity": 2}
    )
    # 하단 밴드 아래로 급락 → entry(BUY)
    candles = [_c(i, 100) for i in range(6)] + [_c(6, 80)]
    sig = strategy.generate_signal("005930", candles, strategy_version_id=1)
    assert sig is not None and sig.side == TradeSide.BUY
    assert sig.quantity == 2
    assert "bollinger_bounce" in sig.reason

    # 평탄 구간 → 신호 없음
    assert strategy.generate_signal("005930", [_c(i, 100) for i in range(8)]) is None


def test_rule_based_invalid_spec_fails_creation():
    with pytest.raises(RuleSpecError):
        create_strategy("rule_based", {"rule_spec": {"name": "x"}})


def test_schema_validates_rule_spec():
    p = StrategyVersionParameters(
        strategy_type="rule_based", symbol_code="005930", rule_spec=BOLLINGER_SPEC
    )
    assert p.rule_spec["name"] == "bollinger_bounce"
    with pytest.raises(pydantic.ValidationError, match="rule_spec 오류"):
        StrategyVersionParameters(
            strategy_type="rule_based", symbol_code="005930",
            rule_spec={"name": "x", "indicators": {}, "entry": None, "exit": None},
        )


# ── 백테스트 통합 (기존 파이프라인 재사용 확인) ──────────────────────────


@pytest.mark.asyncio
async def test_rule_based_backtests_like_any_strategy(db_session: AsyncSession):
    from app.domain.models.market_data import MarketData
    from app.services.backtest_service import BacktestService

    base_ts = datetime(2026, 6, 1, 9, 0, tzinfo=timezone(timedelta(hours=9)))
    closes = [100] * 8 + [80] + [85, 95, 105, 110] + [100] * 5  # 급락 후 반등
    prev = closes[0]
    for i, c in enumerate(closes):
        db_session.add(
            MarketData(
                symbol_code="DSL001", timeframe="1m", ts=base_ts + timedelta(minutes=i),
                open=Decimal(prev), high=Decimal(max(prev, c)),
                low=Decimal(min(prev, c)), close=Decimal(c), volume=1000,
            )
        )
        prev = c
    await db_session.commit()

    run = await BacktestService(db_session).run(
        strategy_type="rule_based",
        parameters={"rule_spec": BOLLINGER_SPEC, "quantity": 1},
        symbol_code="DSL001",
        timeframe="1m",
        start_ts=base_ts,
        end_ts=base_ts + timedelta(hours=1),
    )
    assert run.status == "succeeded"
    assert run.metrics["trade_count"] >= 1  # 급락 매수 → 반등 청산
