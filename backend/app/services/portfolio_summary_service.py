from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.position import Position


def _f(d: Decimal | None) -> float:
    return float(d) if d is not None else 0.0


class PortfolioSummaryService:
    """보유 포지션·노출 집계 (C-3.6, '실전 운영' 가시성).

    현재 보유 포지션(수량≠0)을 시가평가·미실현손익·종목별 노출 비중으로 모아 운영자가
    "지금 무엇을, 얼마나, 어떤 손익으로 들고 있는가"를 한 화면에서 본다.

    read-only 집계 — 주문/외부 호출이 없고 어떤 상태도 바꾸지 않는다. 시세 갱신은 별도
    동기화 잡(order/state sync)의 몫이며, 여기선 저장된 last_price를 그대로 평가에 쓴다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def summary(self, account_id: int | None = None) -> dict:
        stmt = select(Position).where(Position.quantity != 0)
        if account_id is not None:
            stmt = stmt.where(Position.account_id == account_id)
        positions = (await self._session.execute(stmt)).scalars().all()

        rows: list[dict] = []
        total_mv = 0.0
        total_cost = 0.0
        total_unreal = 0.0
        total_realized = 0.0
        for p in positions:
            qty = p.quantity
            avg = _f(p.avg_entry_price)
            last = _f(p.last_price) if p.last_price is not None else avg
            cost_basis = qty * avg
            market_value = qty * last
            unreal = _f(p.unrealized_pnl)
            unreal_pct = round((unreal / cost_basis) * 100, 2) if cost_basis else None
            rows.append({
                "account_id": p.account_id,
                "symbol_code": p.symbol_code,
                "symbol_name": p.symbol_name,
                "quantity": qty,
                "avg_entry_price": round(avg, 4),
                "last_price": round(last, 4),
                "cost_basis": round(cost_basis, 2),
                "market_value": round(market_value, 2),
                "unrealized_pnl": round(unreal, 2),
                "unrealized_pct": unreal_pct,
                "has_price": p.last_price is not None,
            })
            total_mv += market_value
            total_cost += cost_basis
            total_unreal += unreal
            total_realized += _f(p.realized_pnl)

        # 종목별 노출 비중(시가평가 기준). 시총 합이 0이면 비중 None.
        for r in rows:
            r["exposure_pct"] = (
                round((r["market_value"] / total_mv) * 100, 2) if total_mv else None
            )
        rows.sort(key=lambda r: r["market_value"], reverse=True)

        return {
            "open_positions": len(rows),
            "total_market_value": round(total_mv, 2),
            "total_cost_basis": round(total_cost, 2),
            "total_unrealized_pnl": round(total_unreal, 2),
            "total_realized_pnl": round(total_realized, 2),
            "positions": rows,
        }
