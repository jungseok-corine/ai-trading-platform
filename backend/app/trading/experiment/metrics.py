"""Paper 실험 성과 지표 계산 (C-2.26).

체결(trade)의 손익(pnl) 리스트로부터 승률/기대값/손익비/최대낙폭 등을 계산하는 순수 함수.
입력 pnls는 시간순(chronological)으로 정렬되어 있어야 최대낙폭이 올바르게 계산된다.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

_Q = Decimal("0.0001")


@dataclass
class VariantMetrics:
    trades_count: int
    win_count: int
    loss_count: int
    win_rate: Decimal  # 승률 (%, 0~100; 승패가 결정된 거래 기준)
    avg_profit: Decimal  # 평균 수익 (이익 거래 평균, 양수)
    avg_loss: Decimal  # 평균 손실 (손실 거래 평균의 크기, 양수)
    profit_factor: Decimal | None  # 손익비 = 총이익/총손실 (손실 0이면 None)
    expectancy: Decimal  # 기대값 (결정된 거래당 평균 손익)
    max_drawdown: Decimal  # 최대 낙폭 (누적손익 고점 대비 최대 하락, 양수)

    def to_dict(self) -> dict:
        return {
            "trades_count": self.trades_count,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "win_rate": str(self.win_rate),
            "avg_profit": str(self.avg_profit),
            "avg_loss": str(self.avg_loss),
            "profit_factor": str(self.profit_factor) if self.profit_factor is not None else None,
            "expectancy": str(self.expectancy),
            "max_drawdown": str(self.max_drawdown),
        }


def compute_metrics(pnls: list[Decimal]) -> VariantMetrics:
    """시간순 pnl 리스트로부터 실험 지표를 계산한다.

    pnl == 0 인 거래는 승/패에 포함하지 않는다(무승부). 빈 리스트는 모두 0을 반환한다.
    """
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_count = len(wins)
    loss_count = len(losses)
    decided = win_count + loss_count

    gross_profit = sum(wins, Decimal("0"))
    gross_loss = -sum(losses, Decimal("0"))  # 양수 크기

    win_rate = (Decimal(win_count) / decided * 100) if decided else Decimal("0")
    avg_profit = (gross_profit / win_count) if win_count else Decimal("0")
    avg_loss = (gross_loss / loss_count) if loss_count else Decimal("0")
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None
    expectancy = ((gross_profit - gross_loss) / decided) if decided else Decimal("0")
    max_drawdown = _max_drawdown(pnls)

    return VariantMetrics(
        trades_count=len(pnls),
        win_count=win_count,
        loss_count=loss_count,
        win_rate=win_rate.quantize(Decimal("0.01")),
        avg_profit=avg_profit.quantize(_Q),
        avg_loss=avg_loss.quantize(_Q),
        profit_factor=profit_factor.quantize(_Q) if profit_factor is not None else None,
        expectancy=expectancy.quantize(_Q),
        max_drawdown=max_drawdown.quantize(_Q),
    )


def _max_drawdown(pnls: list[Decimal]) -> Decimal:
    """누적손익 곡선의 고점 대비 최대 하락폭(양수)을 반환한다."""
    cum = Decimal("0")
    peak = Decimal("0")
    max_dd = Decimal("0")
    for p in pnls:
        cum += p
        if cum > peak:
            peak = cum
        drawdown = peak - cum
        if drawdown > max_dd:
            max_dd = drawdown
    return max_dd
