from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import RiskEventResult
from app.domain.models.risk import RiskEvent


class RiskEventSummaryService:
    """리스크 이벤트 요약 (C-3.12, '실전 운영' 가시성).

    리스크 레이어가 신호를 승인/차단한 기록을 집계한다. 차단(rejected)이 잦거나 특정 룰에
    몰리면 전략/리스크 설정을 점검할 신호다. read-only 집계 — 주문/외부 호출이 없다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def summary(self, days: int = 30, recent_limit: int = 10) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        events = (
            await self._session.execute(
                select(RiskEvent).where(RiskEvent.created_at >= since)
                .order_by(RiskEvent.created_at.desc(), RiskEvent.id.desc())
            )
        ).scalars().all()

        approved = rejected = 0
        by_rule: dict[str, dict] = {}
        recent_rejections: list[dict] = []
        for e in events:
            is_reject = e.result == RiskEventResult.REJECTED
            if is_reject:
                rejected += 1
            elif e.result == RiskEventResult.APPROVED:
                approved += 1
            rule = e.rule_name or "(미지정)"
            r = by_rule.setdefault(rule, {"rule_name": rule, "approved": 0, "rejected": 0})
            r["rejected" if is_reject else "approved"] += 1
            if is_reject and len(recent_rejections) < recent_limit:
                recent_rejections.append({
                    "rule_name": e.rule_name,
                    "reason": e.reason,
                    "strategy_version_id": e.strategy_version_id,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                })

        total = approved + rejected
        rejection_rate = round(rejected / total * 100, 1) if total else None
        rules = sorted(by_rule.values(), key=lambda x: x["rejected"], reverse=True)
        return {
            "days": days,
            "total": total,
            "approved": approved,
            "rejected": rejected,
            "rejection_rate": rejection_rate,
            "by_rule": rules,
            "recent_rejections": recent_rejections,
        }
