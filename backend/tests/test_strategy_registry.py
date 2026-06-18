"""Strategy Registry/Factory 테스트 (요구사항 #1~4)."""
import logging

import pytest

from app.trading.strategy.moving_average_cross import MovingAverageCrossStrategy
from app.trading.strategy.registry import create_strategy, registered_types
from app.trading.strategy.volume_confirmed_ma_cross import VolumeConfirmedMovingAverageCrossStrategy

MOVING_AVERAGE_PARAMS = {
    "strategy_type": "moving_average_cross",
    "symbol_code": "005930",
    "short_window": 5,
    "long_window": 20,
    "quantity": 1,
}

VOLUME_CONFIRMED_PARAMS = {
    "strategy_type": "volume_confirmed_ma_cross",
    "symbol_code": "005930",
    "short_window": 5,
    "long_window": 20,
    "volume_window": 20,
    "volume_multiplier": 1.5,
    "quantity": 1,
}


# ---------------------------------------------------------------------------
# 테스트 #1: moving_average_cross 등록 확인
# ---------------------------------------------------------------------------


def test_moving_average_cross_is_registered() -> None:
    assert "moving_average_cross" in registered_types()


def test_create_moving_average_cross_strategy() -> None:
    strategy = create_strategy("moving_average_cross", MOVING_AVERAGE_PARAMS)
    assert strategy is not None
    assert isinstance(strategy, MovingAverageCrossStrategy)


# ---------------------------------------------------------------------------
# 테스트 #2: volume_confirmed_ma_cross 등록 확인
# ---------------------------------------------------------------------------


def test_volume_confirmed_ma_cross_is_registered() -> None:
    assert "volume_confirmed_ma_cross" in registered_types()


def test_create_volume_confirmed_ma_cross_strategy() -> None:
    strategy = create_strategy("volume_confirmed_ma_cross", VOLUME_CONFIRMED_PARAMS)
    assert strategy is not None
    assert isinstance(strategy, VolumeConfirmedMovingAverageCrossStrategy)


# ---------------------------------------------------------------------------
# 테스트 #3: unknown strategy_type 안전 skip + warning 로그
# ---------------------------------------------------------------------------


def test_unknown_strategy_type_returns_none(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        result = create_strategy("rsi_strategy", {"symbol_code": "005930"})
    assert result is None


def test_unknown_strategy_type_logs_warning() -> None:
    """알 수 없는 strategy_type 호출 시 logger.warning이 호출되는지 확인한다."""
    from unittest.mock import patch

    with patch("app.trading.strategy.registry.logger") as mock_logger:
        create_strategy("unknown_type_xyz", {"symbol_code": "005930"})
    mock_logger.warning.assert_called_once()
    call_args = str(mock_logger.warning.call_args)
    assert "unknown_type_xyz" in call_args


def test_empty_strategy_type_returns_none() -> None:
    result = create_strategy("", {})
    assert result is None


# ---------------------------------------------------------------------------
# 테스트 #4: from_params가 params dict를 올바르게 읽는지 확인
# ---------------------------------------------------------------------------


def test_moving_average_cross_from_params_reads_windows() -> None:
    strategy = create_strategy("moving_average_cross", {
        "short_window": 3,
        "long_window": 10,
        "quantity": 5,
    })
    assert strategy is not None
    assert isinstance(strategy, MovingAverageCrossStrategy)
    assert strategy._short_window == 3
    assert strategy._long_window == 10
    assert strategy._quantity == 5


def test_volume_confirmed_from_params_reads_volume_params() -> None:
    from decimal import Decimal
    strategy = create_strategy("volume_confirmed_ma_cross", {
        "short_window": 3,
        "long_window": 10,
        "volume_window": 15,
        "volume_multiplier": 2.0,
        "quantity": 2,
    })
    assert strategy is not None
    assert isinstance(strategy, VolumeConfirmedMovingAverageCrossStrategy)
    assert strategy._volume_window == 15
    assert strategy._volume_multiplier == Decimal("2.0")
    assert strategy._quantity == 2


def test_moving_average_cross_from_params_uses_defaults() -> None:
    """파라미터 없이 from_params 호출 시 기본값이 적용된다."""
    strategy = create_strategy("moving_average_cross", {})
    assert strategy is not None
    assert isinstance(strategy, MovingAverageCrossStrategy)
    assert strategy._short_window == 5
    assert strategy._long_window == 20
    assert strategy._quantity == 1
