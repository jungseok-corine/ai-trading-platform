from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from app.domain.models.enums import TradeSide
from app.trading.broker.schemas import MinuteCandle

if TYPE_CHECKING:
    from app.trading.strategy.context import StrategyContext


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
    # 시장 코드(KR/US) — 리스크 검증에서 USD→KRW 환산 등 통화 처리에 사용.
    market: str = "KR"


class Strategy(ABC):
    """시장 데이터를 분석해 매매 Signal을 생성하는 전략 인터페이스.

    구현체는 candles(과거~현재, 오래된 순)을 분석해 Signal을 생성하거나,
    매매 조건을 만족하지 않으면 None을 반환한다. 아직 주문을 실행하지 않는다.
    context(StrategyContext)는 선택적으로 전달되며, 수급 데이터 등 외부 컨텍스트를 담는다.
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
        context: StrategyContext | None = None,
    ) -> Signal | None: ...
