from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import MarketCode
from app.domain.models.strategy_assignment import (
    StrategyAssignmentLog,
    StrategyAssignmentRule,
)
from app.domain.repositories.candidate_event import CandidateEventRepository
from app.domain.repositories.scanner import ScannerRuleVersionRepository
from app.domain.repositories.strategy_assignment import (
    StrategyAssignmentLogRepository,
    StrategyAssignmentRuleRepository,
)
from app.trading.strategy.registry import registered_types


class InvalidStrategyTypeError(Exception):
    """등록되지 않은 strategy_type을 배정 규칙에 지정했을 때 발생."""


class CandidateEventNotFoundError(Exception):
    """candidate_event_id가 존재하지 않을 때 발생."""


class AssignmentService:
    """후보 종목(candidate_event)에 전략을 배정하는 규칙을 관리하고 배정을 수행한다.

    C-2.25 Foundation: 배정 결정을 strategy_assignment_log로 기록한다. 이 단계에서는
    strategy_version을 자동 생성하지 않는다(버전 폭발 방지). 실제 paper 실험은 이후 단계.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._rule_repo = StrategyAssignmentRuleRepository(session)
        self._log_repo = StrategyAssignmentLogRepository(session)
        self._candidate_repo = CandidateEventRepository(session)
        self._version_repo = ScannerRuleVersionRepository(session)

    async def create_rule(
        self,
        name: str,
        strategy_type: str,
        market: MarketCode = MarketCode.KR,
        scanner_rule_id: int | None = None,
        default_parameters: dict | None = None,
        priority: int = 0,
        description: str | None = None,
    ) -> StrategyAssignmentRule:
        if strategy_type not in registered_types():
            raise InvalidStrategyTypeError(
                f"unknown strategy_type {strategy_type!r}. "
                f"registered: {sorted(registered_types())}"
            )
        rule = await self._rule_repo.create(
            name=name,
            strategy_type=strategy_type,
            market=market,
            scanner_rule_id=scanner_rule_id,
            default_parameters=default_parameters,
            priority=priority,
            description=description,
        )
        await self._session.commit()
        return rule

    async def list_rules(
        self, market: MarketCode | None = None
    ) -> list[StrategyAssignmentRule]:
        return await self._rule_repo.list_all(market=market)

    async def assign(self, candidate_event_id: int) -> StrategyAssignmentLog | None:
        """후보에 매칭되는 배정 규칙을 찾아 전략을 배정하고 로그를 남긴다.

        매칭되는 규칙이 없으면 None을 반환한다(배정 안 됨).
        """
        candidate = await self._candidate_repo.get(candidate_event_id)
        if candidate is None:
            raise CandidateEventNotFoundError(candidate_event_id)

        version = await self._version_repo.get(candidate.scanner_rule_version_id)
        scanner_rule_id = version.scanner_rule_id if version is not None else None

        rule: StrategyAssignmentRule | None = None
        if scanner_rule_id is not None:
            rule = await self._rule_repo.find_matching(scanner_rule_id, candidate.market)
        if rule is None:
            return None

        assigned_parameters = {
            **(rule.default_parameters or {}),
            "strategy_type": rule.strategy_type,
            "symbol_code": candidate.symbol_code,
        }
        log = await self._log_repo.create(
            candidate_event_id=candidate.id,
            strategy_assignment_rule_id=rule.id,
            market=candidate.market,
            symbol_code=candidate.symbol_code,
            strategy_type=rule.strategy_type,
            assigned_parameters=assigned_parameters,
        )
        await self._session.commit()
        return log

    async def list_logs(
        self,
        candidate_event_id: int | None = None,
        symbol_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StrategyAssignmentLog]:
        return await self._log_repo.list_filtered(
            candidate_event_id=candidate_event_id,
            symbol_code=symbol_code,
            limit=limit,
            offset=offset,
        )
