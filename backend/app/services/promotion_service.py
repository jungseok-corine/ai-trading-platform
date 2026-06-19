from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import MarketCode
from app.domain.models.promotion import PromotionCriteria, PromotionEvaluation
from app.domain.repositories.promotion import (
    PromotionCriteriaRepository,
    PromotionEvaluationRepository,
)
from app.domain.repositories.strategy import StrategyVersionRepository
from app.domain.repositories.trade import TradeRepository
from app.trading.experiment.metrics import compute_metrics


class PromotionCriteriaNotFoundError(Exception):
    """criteria_id가 존재하지 않을 때 발생."""


class StrategyVersionNotFoundError(Exception):
    """strategy_version_id가 존재하지 않을 때 발생."""


@dataclass
class CheckResult:
    name: str
    passed: bool
    actual: str
    threshold: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "actual": self.actual,
            "threshold": self.threshold,
        }


@dataclass
class PromotionResult:
    strategy_version_id: int
    criteria_id: int
    passed: bool
    trades_count: int
    days: int
    expectancy: Decimal
    max_drawdown: Decimal
    checks: list[CheckResult] = field(default_factory=list)


class PromotionService:
    """paper → 실전 승격 기준을 관리하고, 전략 버전을 평가한다 (C-2.30).

    ⚠️ 안전 원칙: 이 게이트 통과는 '실전 적용 가능 여부 판단'일 뿐이다. AI/시스템이 실거래를
    자동으로 켜지 않는다. 실전 활성화는 항상 사람의 명시적 확인 + KIS_REAL_TRADING_ENABLED +
    TradingGuard 해제가 필요하다(문서 10장 / 13.3).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._criteria_repo = PromotionCriteriaRepository(session)
        self._eval_repo = PromotionEvaluationRepository(session)
        self._version_repo = StrategyVersionRepository(session)
        self._trade_repo = TradeRepository(session)

    async def create_criteria(
        self,
        name: str,
        market: MarketCode = MarketCode.KR,
        min_trade_count: int = 50,
        min_days: int = 30,
        min_expectancy: Decimal = Decimal("0"),
        max_drawdown: Decimal | None = None,
    ) -> PromotionCriteria:
        criteria = await self._criteria_repo.create(
            name=name,
            market=market,
            min_trade_count=min_trade_count,
            min_days=min_days,
            min_expectancy=min_expectancy,
            max_drawdown=max_drawdown,
        )
        await self._session.commit()
        return criteria

    async def list_criteria(
        self, market: MarketCode | None = None
    ) -> list[PromotionCriteria]:
        return await self._criteria_repo.list_all(market=market)

    async def evaluate(
        self, strategy_version_id: int, criteria_id: int, persist: bool = False
    ) -> PromotionResult:
        version = await self._version_repo.get(strategy_version_id)
        if version is None:
            raise StrategyVersionNotFoundError(strategy_version_id)
        criteria = await self._criteria_repo.get(criteria_id)
        if criteria is None:
            raise PromotionCriteriaNotFoundError(criteria_id)

        trades = await self._trade_repo.list_by_strategy_version(strategy_version_id)
        chronological = list(reversed(trades))  # list_by_strategy_version은 created_at 내림차순
        pnls = [t.pnl_amount for t in chronological if t.pnl_amount is not None]
        metrics = compute_metrics(pnls)

        days = 0
        if len(chronological) >= 2:
            days = (chronological[-1].created_at - chronological[0].created_at).days

        checks = [
            CheckResult(
                "min_trade_count",
                metrics.trades_count >= criteria.min_trade_count,
                str(metrics.trades_count),
                str(criteria.min_trade_count),
            ),
            CheckResult(
                "min_days",
                days >= criteria.min_days,
                str(days),
                str(criteria.min_days),
            ),
            CheckResult(
                "min_expectancy",
                metrics.expectancy >= criteria.min_expectancy,
                str(metrics.expectancy),
                str(criteria.min_expectancy),
            ),
        ]
        if criteria.max_drawdown is not None:
            checks.append(
                CheckResult(
                    "max_drawdown",
                    metrics.max_drawdown <= criteria.max_drawdown,
                    str(metrics.max_drawdown),
                    str(criteria.max_drawdown),
                )
            )

        passed = all(c.passed for c in checks)
        result = PromotionResult(
            strategy_version_id=strategy_version_id,
            criteria_id=criteria_id,
            passed=passed,
            trades_count=metrics.trades_count,
            days=days,
            expectancy=metrics.expectancy,
            max_drawdown=metrics.max_drawdown,
            checks=checks,
        )

        if persist:
            await self._eval_repo.create(
                strategy_version_id=strategy_version_id,
                criteria_id=criteria_id,
                passed=passed,
                trades_count=metrics.trades_count,
                days=days,
                expectancy=metrics.expectancy,
                max_drawdown=metrics.max_drawdown,
                checks=[c.to_dict() for c in checks],
            )
            await self._session.commit()

        return result

    async def list_evaluations(
        self, strategy_version_id: int, limit: int = 50
    ) -> list[PromotionEvaluation]:
        return await self._eval_repo.list_by_version(strategy_version_id, limit=limit)
