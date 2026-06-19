import logging

from app.trading.strategy.base import Strategy
from app.trading.strategy.flow_confirmed_volume_ma_cross import FlowConfirmedVolumeMACrossStrategy
from app.trading.strategy.moving_average_cross import MovingAverageCrossStrategy
from app.trading.strategy.volume_confirmed_ma_cross import VolumeConfirmedMovingAverageCrossStrategy

logger = logging.getLogger(__name__)

# strategy_type 문자열 → Strategy 클래스 매핑.
# 새 전략 추가 시 여기에만 등록하면 runner 수정 없이 실행된다.
_REGISTRY: dict[str, type[Strategy]] = {
    MovingAverageCrossStrategy.name: MovingAverageCrossStrategy,
    VolumeConfirmedMovingAverageCrossStrategy.name: VolumeConfirmedMovingAverageCrossStrategy,
    FlowConfirmedVolumeMACrossStrategy.name: FlowConfirmedVolumeMACrossStrategy,
}


def create_strategy(strategy_type: str, params: dict) -> Strategy | None:
    """strategy_type에 해당하는 Strategy 인스턴스를 from_params로 생성한다.

    알 수 없는 strategy_type은 None을 반환하고 warning을 로그한다. 예외를 raise하지 않는다.
    """
    cls = _REGISTRY.get(strategy_type)
    if cls is None:
        logger.warning("알 수 없는 strategy_type=%r — 건너뜁니다.", strategy_type)
        return None
    return cls.from_params(params)


def registered_types() -> list[str]:
    """등록된 strategy_type 목록을 반환한다."""
    return list(_REGISTRY.keys())
