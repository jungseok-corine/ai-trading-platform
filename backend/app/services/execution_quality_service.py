"""체결 품질(슬리피지·지연) 측정 (C-6.9).

신호 가격(signal_logs.price)과 실제 체결 가격(trades.entry_price)의 차이,
신호 생성→체결 기록 지연을 집계한다. read-only — 실전 배치 전 실행 품질 근거.

슬리피지 부호 규약 (양수 = 불리):
- BUY: (체결가 - 신호가) / 신호가 × 100  → 비싸게 샀으면 양수
- SELL: (신호가 - 체결가) / 신호가 × 100 → 싸게 팔았으면 양수
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import OrderStatus, TradeSide
from app.domain.models.signal_log import SignalLog
from app.domain.models.trade import Trade


class ExecutionQualityService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def summary(self, days: int = 30) -> dict[str, Any]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(SignalLog, Trade)
            .join(Trade, SignalLog.trade_id == Trade.id)
            .where(
                SignalLog.generated_at >= cutoff,
                SignalLog.price.is_not(None),
                Trade.entry_price.is_not(None),
                Trade.order_status.in_([OrderStatus.FILLED, OrderStatus.PARTIAL]),
            )
            .order_by(SignalLog.generated_at.desc())
            .limit(1000)
        )
        rows = (await self._session.execute(stmt)).all()

        pairs: list[dict[str, Any]] = []
        for log, trade in rows:
            if log.price is None or log.price <= 0 or trade.entry_price is None:
                continue
            raw = (trade.entry_price - log.price) / log.price * 100
            slippage_pct = float(raw if trade.side == TradeSide.BUY else -raw)
            latency = (
                (trade.entry_time - log.generated_at).total_seconds()
                if trade.entry_time is not None
                else None
            )
            pairs.append(
                {
                    "signal_id": log.id,
                    "trade_id": trade.id,
                    "symbol_code": trade.symbol_code,
                    "market": trade.market,
                    "side": trade.side.value,
                    "strategy_version_id": trade.strategy_version_id,
                    "signal_price": float(log.price),
                    "fill_price": float(trade.entry_price),
                    "slippage_pct": round(slippage_pct, 4),
                    "latency_seconds": latency,
                    "generated_at": log.generated_at.isoformat(),
                }
            )

        return {
            "days": days,
            "pair_count": len(pairs),
            "aggregate": self._aggregate(pairs),
            "by_side": {
                side: self._aggregate([p for p in pairs if p["side"] == side])
                for side in ("buy", "sell")
            },
            # 가장 불리했던 체결 5건 — 원인 조사 진입점
            "worst": sorted(pairs, key=lambda p: p["slippage_pct"], reverse=True)[:5],
            "note": "양수 슬리피지 = 불리한 체결 (BUY는 비싸게, SELL은 싸게). read-only 집계.",
        }

    @staticmethod
    def _aggregate(pairs: list[dict[str, Any]]) -> dict[str, Any]:
        if not pairs:
            return {"count": 0}
        slips = [p["slippage_pct"] for p in pairs]
        latencies = [p["latency_seconds"] for p in pairs if p["latency_seconds"] is not None]
        return {
            "count": len(pairs),
            "avg_slippage_pct": round(sum(slips) / len(slips), 4),
            "median_slippage_pct": round(median(slips), 4),
            "max_slippage_pct": round(max(slips), 4),
            "adverse_fill_ratio": round(sum(1 for s in slips if s > 0) / len(slips), 4),
            "avg_latency_seconds": (
                round(sum(latencies) / len(latencies), 2) if latencies else None
            ),
        }
