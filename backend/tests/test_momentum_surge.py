"""C-5.15: 급등 모멘텀 전략 — 단기 급등 + 거래량 급증 시 진입, 모멘텀 소멸 시 청산."""
from decimal import Decimal

from app.domain.models.enums import TradeSide
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.momentum_surge import MomentumSurgeStrategy


def _candles(closes: list[float], volumes: list[int]) -> list[MinuteCandle]:
    out = []
    for i, (c, v) in enumerate(zip(closes, volumes)):
        p = Decimal(str(c))
        out.append(MinuteCandle(
            business_date="20260622", trade_time=f"2230{i:02d}",
            open_price=p, high_price=p, low_price=p, close_price=p, volume=v,
        ))
    return out


def _strat(**kw) -> MomentumSurgeStrategy:
    return MomentumSurgeStrategy.from_params({
        "surge_lookback": 3, "surge_threshold_pct": 5.0, "exit_drop_pct": 3.0,
        "volume_window": 5, "volume_multiplier": 2.0, **kw,
    })


def test_buy_on_surge_with_volume() -> None:
    # 마지막 3봉에서 +10% 급등 + 마지막 봉 거래량 급증 → 매수
    closes = [100, 100, 100, 100, 100, 100, 105, 110]  # 5봉전 100 → 110 = +10%
    volumes = [100] * 7 + [500]  # 마지막 거래량 급증(평균 대비 ~5x)
    sig = _strat().generate_signal("AAPL", _candles(closes, volumes))
    assert sig is not None
    assert sig.side == TradeSide.BUY
    assert "급등 진입" in sig.reason


def test_no_buy_without_volume_surge() -> None:
    # 급등은 했지만 거래량이 평범 → 매수 안 함(noise 억제)
    closes = [100, 100, 100, 100, 100, 100, 105, 110]
    volumes = [100] * 8  # 거래량 급증 없음
    sig = _strat().generate_signal("AAPL", _candles(closes, volumes))
    assert sig is None


def test_sell_on_momentum_fade() -> None:
    # 최근 3봉 -8% 하락 → 모멘텀 소멸 청산
    closes = [100, 100, 100, 100, 110, 108, 104, 101]  # 3봉전 110 → 101 ≈ -8.2%
    volumes = [100] * 8
    sig = _strat().generate_signal("AAPL", _candles(closes, volumes))
    assert sig is not None
    assert sig.side == TradeSide.SELL
    assert "모멘텀 소멸" in sig.reason


def test_none_when_flat() -> None:
    closes = [100] * 8
    volumes = [100] * 8
    assert _strat().generate_signal("AAPL", _candles(closes, volumes)) is None


def test_registered_in_registry() -> None:
    from app.trading.strategy.registry import create_strategy

    s = create_strategy("momentum_surge", {"surge_lookback": 5})
    assert isinstance(s, MomentumSurgeStrategy)
