from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.domain.models.enums import TradeSide
from app.trading.broker.schemas import MinuteCandle


@dataclass
class Signal:
    """Strategy가 생성하는 매매 신호. RiskManager.validate()의 입력이 된다."""

    symbol_code: str
    side: TradeSide
    quantity: int
    price: Decimal
    reason: str
    strategy_version_id: int | None = None
    metadata: dict[str, Any] | None = None


class Strategy(ABC):
    """시장 데이터를 분석해 매매 Signal을 생성하는 전략 인터페이스.

    구현체는 candles(과거~현재, 오래된 순)을 분석해 Signal을 생성하거나,
    매매 조건을 만족하지 않으면 None을 반환한다. 아직 주문을 실행하지 않는다.
    """

    @classmethod
    @abstractmethod
    def from_params(cls, params: dict) -> "Strategy":
        """strategy_versions.parameters dict에서 전략 인스턴스를 생성한다."""
        ...

    @abstractmethod
    def generate_signal(
        self,
        symbol_code: str,
        candles: list[MinuteCandle],
        strategy_version_id: int | None = None,
    ) -> Signal | None: ...
