from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.promotion import PromotionCriteria
from app.domain.models.strategy import Strategy, StrategyVersion
from app.services.promotion_service import PromotionService


class PromotionReadinessService:
    """승격 준비 현황 보드 (C-3.13).

    활성/테스트 전략 버전을 골라 승격 기준(promotion_criteria)에 얼마나 근접했는지 한눈에
    보여준다. ⚠️ 이 보드는 '판단'일 뿐 — 통과해도 실거래가 켜지지 않는다. 실전 활성화는
    항상 사람의 명시적 확인이 필요하다(안전 불변식). read-only 평가(persist=False).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._promotion = PromotionService(session)

    async def board(self, criteria_id: int | None = None) -> dict:
        criteria = await self._pick_criteria(criteria_id)
        if criteria is None:
            return {"criteria": None, "rows": [], "note": "승격 기준이 없습니다. 먼저 기준을 등록하세요."}

        rows_q = (
            await self._session.execute(
                select(StrategyVersion.id, Strategy.name, StrategyVersion.version_no,
                       StrategyVersion.status)
                .join(Strategy, Strategy.id == StrategyVersion.strategy_id)
                .where(StrategyVersion.status.in_(
                    [StrategyVersionStatus.ACTIVE, StrategyVersionStatus.TESTING]
                ))
            )
        ).all()

        rows: list[dict] = []
        for vid, name, vno, status in rows_q:
            result = await self._promotion.evaluate(vid, criteria.id, persist=False)
            checks = [c.to_dict() for c in result.checks]
            passed_checks = sum(1 for c in checks if c["passed"])
            rows.append({
                "strategy_version_id": vid,
                "label": f"{name} v{vno}",
                "status": status.value,
                "passed": result.passed,
                "checks_passed": passed_checks,
                "checks_total": len(checks),
                "trades_count": result.trades_count,
                "days": result.days,
                "expectancy": float(result.expectancy),
                "max_drawdown": float(result.max_drawdown),
                "checks": checks,
            })
        # 통과 우선, 그다음 충족 체크 많은 순
        rows.sort(key=lambda r: (r["passed"], r["checks_passed"]), reverse=True)

        return {
            "criteria": {
                "id": criteria.id,
                "name": criteria.name,
                "market": criteria.market.value,
                "min_trade_count": criteria.min_trade_count,
                "min_days": criteria.min_days,
                "min_expectancy": float(criteria.min_expectancy),
                "max_drawdown": float(criteria.max_drawdown) if criteria.max_drawdown is not None else None,
            },
            "rows": rows,
            "note": "통과는 '실전 적용 가능 판단'일 뿐 — 실거래 활성화는 사람만 합니다.",
        }

    async def ready_count(self, criteria_id: int | None = None) -> int:
        """승격 기준을 통과한 활성/테스트 버전 수(요약용). 기준 없으면 0."""
        board = await self.board(criteria_id=criteria_id)
        return sum(1 for r in board["rows"] if r["passed"])

    async def _pick_criteria(self, criteria_id: int | None) -> PromotionCriteria | None:
        stmt = select(PromotionCriteria)
        if criteria_id is not None:
            stmt = stmt.where(PromotionCriteria.id == criteria_id)
        else:
            stmt = stmt.order_by(PromotionCriteria.id).limit(1)
        return (await self._session.execute(stmt)).scalars().first()
