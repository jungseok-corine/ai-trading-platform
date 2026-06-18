"""VolumeConfirmedMovingAverageCrossStrategy 테스트 (요구사항 #10~12)."""
from decimal import Decimal

import pytest

from app.domain.models.enums import TradeSide
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.volume_confirmed_ma_cross import VolumeConfirmedMovingAverageCrossStrategy


def _make_candles(
    closes: list[int | float],
    volumes: list[int] | None = None,
) -> list[MinuteCandle]:
    if volumes is None:
        volumes = [1000] * len(closes)
    candles = []
    for i, (close, vol) in enumerate(zip(closes, volumes)):
        price = Decimal(str(close))
        candles.append(
            MinuteCandle(
                business_date="20260610",
                trade_time=f"{900 + i:04d}00",
                open_price=price,
                high_price=price,
                low_price=price,
                close_price=price,
                volume=vol,
            )
        )
    return candles


def _make_golden_cross_candles(volume_spike: bool = True) -> list[MinuteCandle]:
    """short=5, long=20 기준 골든크로스 데이터 생성.

    처음 20개: close=100, volume=1000 (평탄)
    마지막 1개: close=200 (급등) + volume 조건
    """
    closes = [100] * 20 + [200]
    normal_vol = 1000
    spike_vol = 2000 if volume_spike else 500  # 2000 >= 1000*1.5=1500 OK, 500 < 1500 NG
    volumes = [normal_vol] * 20 + [spike_vol]
    return _make_candles(closes, volumes)


# ---------------------------------------------------------------------------
# 테스트 #10: BUY 조건 — 골든크로스 + 거래량 확인
# ---------------------------------------------------------------------------


def test_buy_signal_on_golden_cross_with_volume_spike() -> None:
    strategy = VolumeConfirmedMovingAverageCrossStrategy(
        short_window=5, long_window=20, volume_window=20, volume_multiplier=Decimal("1.5")
    )
    candles = _make_golden_cross_candles(volume_spike=True)

    signal = strategy.generate_signal("005930", candles, strategy_version_id=1)

    assert signal is not None
    assert signal.side == TradeSide.BUY
    assert signal.symbol_code == "005930"
    assert signal.strategy_version_id == 1
    assert signal.metadata is not None
    assert signal.metadata["volume_confirmed"] is True
    assert signal.metadata["volume_ratio"] is not None
    assert signal.metadata["volume_ratio"] >= Decimal("1.5")


def test_buy_signal_metadata_has_required_keys() -> None:
    strategy = VolumeConfirmedMovingAverageCrossStrategy(
        short_window=5, long_window=20, volume_window=20, volume_multiplier=Decimal("1.5")
    )
    candles = _make_golden_cross_candles(volume_spike=True)
    signal = strategy.generate_signal("005930", candles)
    assert signal is not None
    meta = signal.metadata or {}
    for key in ("short_sma", "long_sma", "current_volume", "volume_sma", "volume_ratio", "volume_confirmed"):
        assert key in meta, f"metadata에 {key!r} 키가 없습니다"


# ---------------------------------------------------------------------------
# 테스트 #11: 거래량 조건 미충족 시 BUY 방지
# ---------------------------------------------------------------------------


def test_no_buy_signal_when_volume_insufficient() -> None:
    """골든크로스가 발생해도 거래량이 부족하면 신호가 없어야 한다."""
    strategy = VolumeConfirmedMovingAverageCrossStrategy(
        short_window=5, long_window=20, volume_window=20, volume_multiplier=Decimal("1.5")
    )
    candles = _make_golden_cross_candles(volume_spike=False)

    signal = strategy.generate_signal("005930", candles)

    assert signal is None


def test_volume_confirmed_false_in_metadata_when_no_spike() -> None:
    """거래량 미충족 케이스에서 volume_confirmed=False임을 직접 계산으로 확인."""
    from app.trading.strategy.indicators import calculate_volume_ratio, calculate_volume_sma

    closes = [100] * 20 + [200]
    volumes = [1000] * 20 + [500]
    candles = _make_candles(closes, volumes)

    vsma = calculate_volume_sma(candles, 20)
    vr = calculate_volume_ratio(candles, 20)
    assert vsma is not None
    assert vr is not None
    assert vr < Decimal("1.5")  # 500 / ((1000*20+500)/20+1) < 1.5


# ---------------------------------------------------------------------------
# 테스트 #12: 기존 MovingAverageCrossStrategy 회귀 테스트
# ---------------------------------------------------------------------------


def test_existing_ma_cross_golden_cross_still_works() -> None:
    """VolumeConfirmed 도입 후에도 기존 MA cross 전략이 그대로 동작한다."""
    from app.trading.strategy.moving_average_cross import MovingAverageCrossStrategy

    strategy = MovingAverageCrossStrategy(short_window=5, long_window=20)
    closes = [100] * 20 + [200]
    candles = _make_candles(closes)

    signal = strategy.generate_signal("005930", candles, strategy_version_id=99)

    assert signal is not None
    assert signal.side == TradeSide.BUY
    assert signal.strategy_version_id == 99
    assert signal.metadata is not None
    assert signal.metadata["short_ma"] > signal.metadata["long_ma"]


def test_existing_ma_cross_dead_cross_still_works() -> None:
    from app.trading.strategy.moving_average_cross import MovingAverageCrossStrategy

    strategy = MovingAverageCrossStrategy(short_window=5, long_window=20)
    closes = [100] * 20 + [0]
    candles = _make_candles(closes)

    signal = strategy.generate_signal("005930", candles)

    assert signal is not None
    assert signal.side == TradeSide.SELL


def test_existing_ma_cross_no_signal_when_flat() -> None:
    from app.trading.strategy.moving_average_cross import MovingAverageCrossStrategy

    strategy = MovingAverageCrossStrategy(short_window=5, long_window=20)
    candles = _make_candles([100] * 21)

    assert strategy.generate_signal("005930", candles) is None


# ---------------------------------------------------------------------------
# SELL 신호 — 거래량 무관 데드크로스
# ---------------------------------------------------------------------------


def test_sell_signal_on_dead_cross_without_volume_spike() -> None:
    """SELL은 거래량과 무관하게 데드크로스만으로 발생한다."""
    strategy = VolumeConfirmedMovingAverageCrossStrategy(
        short_window=5, long_window=20, volume_window=20, volume_multiplier=Decimal("1.5")
    )
    closes = [100] * 20 + [0]
    volumes = [500] * 21  # 거래량 낮음
    candles = _make_candles(closes, volumes)

    signal = strategy.generate_signal("005930", candles)

    assert signal is not None
    assert signal.side == TradeSide.SELL


# ---------------------------------------------------------------------------
# 데이터 부족 케이스
# ---------------------------------------------------------------------------


def test_insufficient_candles_returns_none() -> None:
    strategy = VolumeConfirmedMovingAverageCrossStrategy(short_window=5, long_window=20)
    candles = _make_candles([100] * 10)
    assert strategy.generate_signal("005930", candles) is None


def test_no_cross_returns_none() -> None:
    strategy = VolumeConfirmedMovingAverageCrossStrategy(short_window=5, long_window=20)
    candles = _make_candles([100] * 22)  # 평탄 → 교차 없음
    assert strategy.generate_signal("005930", candles) is None
