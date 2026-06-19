from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.models.investor_flow import InvestorFlow


@dataclass
class StrategyContext:
    """전략에 주입되는 외부 컨텍스트 데이터.

    전략 클래스는 DB/네트워크에 직접 접근하지 않는다.
    candles를 조회하는 서비스 레이어(SignalService)가 조립해서 전달한다.
    """

    latest_investor_flow: InvestorFlow | None = None
    investor_flows: list[InvestorFlow] = field(default_factory=list)
    flow_data_available: bool = False
    flow_data_date: date | None = None
    flow_data_staleness_days: int | None = None
