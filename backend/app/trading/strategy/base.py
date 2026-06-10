from dataclasses import dataclass
from decimal import Decimal

from app.domain.models.enums import TradeSide


@dataclass
class Signal:
    """Strategy가 생성하는 매매 신호. RiskManager.validate()의 입력이 된다."""

    symbol_code: str
    side: TradeSide
    quantity: int
    price: Decimal
    reason: str
    strategy_version_id: int | None = None
