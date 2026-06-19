from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import MarketCode, ScannerRuleStatus
from app.domain.models.scanner import ScannerRule, ScannerRuleVersion
from app.domain.repositories.scanner import (
    ScannerRuleRepository,
    ScannerRuleVersionRepository,
)
from app.trading.scanner.conditions import (
    ScannerEvalResult,
    evaluate_conditions,
    validate_conditions,
)


class ScannerRuleNotFoundError(Exception):
    """scanner_rule_id가 존재하지 않을 때 발생."""


class ScannerRuleVersionNotFoundError(Exception):
    """scanner_rule_id 하위에 version_id가 존재하지 않을 때 발생."""


class ScannerService:
    """스캐너 룰/버전 생성·조회·평가를 담당한다.

    C-2.23 Foundation: 감시 조건을 DB에 저장하고, 미리 계산된 facts에 대해 룰을
    평가(evaluate)할 수 있다. 시장 전체 스캔(모든 종목 순회)과 facts 계산은 이후 단계.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._rule_repo = ScannerRuleRepository(session)
        self._version_repo = ScannerRuleVersionRepository(session)

    async def create_rule(
        self,
        name: str,
        market: MarketCode = MarketCode.KR,
        description: str | None = None,
    ) -> ScannerRule:
        rule = await self._rule_repo.create(
            name=name, market=market, description=description
        )
        await self._session.commit()
        return rule

    async def list_rules(
        self, market: MarketCode | None = None
    ) -> list[tuple[ScannerRule, int]]:
        return await self._rule_repo.list_with_version_counts(market=market)

    async def create_version(
        self,
        scanner_rule_id: int,
        conditions: list[dict],
        change_description: str | None = None,
        status: ScannerRuleStatus = ScannerRuleStatus.DRAFT,
    ) -> ScannerRuleVersion:
        """룰 버전을 생성한다. conditions는 저장 전에 검증된다.

        검증 실패 시 InvalidConditionError(ValueError)를 발생시킨다.
        """
        rule = await self._rule_repo.get(scanner_rule_id)
        if rule is None:
            raise ScannerRuleNotFoundError(scanner_rule_id)

        validated = validate_conditions(conditions)
        normalized = [c.model_dump(mode="json") for c in validated]

        next_no = await self._version_repo.get_max_version_no(scanner_rule_id) + 1
        version = await self._version_repo.create(
            scanner_rule_id=scanner_rule_id,
            version_no=next_no,
            conditions=normalized,
            change_description=change_description,
            status=status,
        )
        await self._session.commit()
        return version

    async def list_versions(
        self, scanner_rule_id: int, include_archived: bool = False
    ) -> list[ScannerRuleVersion]:
        rule = await self._rule_repo.get(scanner_rule_id)
        if rule is None:
            raise ScannerRuleNotFoundError(scanner_rule_id)
        return await self._version_repo.list_by_rule(
            scanner_rule_id, include_archived=include_archived
        )

    async def update_version_status(
        self, scanner_rule_id: int, version_id: int, status: ScannerRuleStatus
    ) -> ScannerRuleVersion:
        version = await self._get_owned_version(scanner_rule_id, version_id)
        await self._version_repo.update(version, status=status)
        await self._session.commit()
        return version

    async def evaluate(
        self, scanner_rule_id: int, version_id: int, facts: dict[str, Any]
    ) -> ScannerEvalResult:
        """저장된 룰 버전의 조건을 facts에 대해 평가한다."""
        version = await self._get_owned_version(scanner_rule_id, version_id)
        return evaluate_conditions(version.conditions, facts)

    async def _get_owned_version(
        self, scanner_rule_id: int, version_id: int
    ) -> ScannerRuleVersion:
        version = await self._version_repo.get(version_id)
        if version is None or version.scanner_rule_id != scanner_rule_id:
            raise ScannerRuleVersionNotFoundError(version_id)
        return version
