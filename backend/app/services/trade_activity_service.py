from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.trade import Trade


def _f(d) -> float:
    return float(d) if d is not None else 0.0


class TradeActivityService:
    """거래 활동 요약 (C-3.11, '실전 운영' 가시성).

    최근 거래의 건수·승패·손익을 전체/전략별로 모은다. 청산 손익(pnl_amount)이 기록된
    거래만 승패·손익 집계에 넣고, 미청산/미체결은 건수에만 반영한다.
    read-only 집계 — 주문/외부 호출이 없다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def summary(self, days: int = 30) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        trades = (
            await self._session.execute(select(Trade).where(Trade.created_at >= since))
        ).scalars().all()

        overall = _empty_bucket()
        by_version: dict[int | None, dict] = {}
        for t in trades:
            _accumulate(overall, t)
            b = by_version.setdefault(t.strategy_version_id, _empty_bucket())
            _accumulate(b, t)

        _finalize(overall)
        # 전략 버전 라벨 붙이기
        labels = await self._version_labels([v for v in by_version if v is not None])
        by_strategy = []
        for version_id, b in by_version.items():
            _finalize(b)
            by_strategy.append({
                "strategy_version_id": version_id,
                "label": labels.get(version_id, "미지정" if version_id is None else f"v{version_id}"),
                **b,
            })
        by_strategy.sort(key=lambda x: x["total_pnl"], reverse=True)

        return {"days": days, "overall": overall, "by_strategy": by_strategy}

    async def equity_curve(self, days: int = 30) -> list[dict]:
        """일자별 실현손익과 누적 손익(에쿼티 곡선)을 반환한다.

        청산 손익(pnl_amount)이 기록된 거래만 쓴다. 거래일(exit_time 우선, 없으면 created_at)
        기준으로 묶는다. read-only 집계.
        """
        since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        trades = (
            await self._session.execute(select(Trade).where(Trade.created_at >= since))
        ).scalars().all()

        by_day: dict[str, float] = {}
        for t in trades:
            if t.pnl_amount is None:
                continue
            ts = t.exit_time or t.created_at
            day = ts.date().isoformat() if ts else "unknown"
            by_day[day] = round(by_day.get(day, 0.0) + _f(t.pnl_amount), 2)

        curve: list[dict] = []
        cumulative = 0.0
        for day in sorted(by_day):
            cumulative = round(cumulative + by_day[day], 2)
            curve.append({"date": day, "realized_pnl": by_day[day], "cumulative_pnl": cumulative})
        return curve

    async def _version_labels(self, version_ids: list[int]) -> dict[int, str]:
        if not version_ids:
            return {}
        rows = (
            await self._session.execute(
                select(StrategyVersion.id, Strategy.name, StrategyVersion.version_no)
                .join(Strategy, Strategy.id == StrategyVersion.strategy_id)
                .where(StrategyVersion.id.in_(version_ids))
            )
        ).all()
        return {vid: f"{name} v{vno}" for vid, name, vno in rows}


def _empty_bucket() -> dict:
    return {
        "trades": 0, "closed": 0, "wins": 0, "losses": 0,
        "total_pnl": 0.0, "win_rate": None, "avg_pnl": None,
    }


def _accumulate(b: dict, t: Trade) -> None:
    b["trades"] += 1
    if t.pnl_amount is not None:
        pnl = _f(t.pnl_amount)
        b["closed"] += 1
        b["total_pnl"] = round(b["total_pnl"] + pnl, 2)
        if pnl > 0:
            b["wins"] += 1
        elif pnl < 0:
            b["losses"] += 1


def _finalize(b: dict) -> None:
    if b["closed"]:
        decided = b["wins"] + b["losses"]
        b["win_rate"] = round(b["wins"] / decided * 100, 1) if decided else None
        b["avg_pnl"] = round(b["total_pnl"] / b["closed"], 2)
