from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.enums import MarketCode
from app.domain.repositories.candidate_event import CandidateEventRepository
from app.domain.repositories.scanner import (
    ScannerRuleRepository,
    ScannerRuleVersionRepository,
)
from app.services.scanner_service import ScannerRuleVersionNotFoundError
from app.trading.scanner.conditions import evaluate_conditions
from app.trading.scanner.macro_score import macro_score_adjustment


@dataclass
class ScanResult:
    """1회 스캔 결과 요약."""

    scanner_rule_version_id: int
    scanned: int  # 평가한 종목 수
    matched: int  # 조건을 모두 충족한 종목 수
    candidates: list[CandidateEvent]


class CandidateService:
    """스캐너 룰 버전을 종목별 facts에 대해 평가하고, 매칭된 종목을 candidate_event로 기록한다.

    C-2.24 Foundation: facts는 호출자가 제공한다(시장 데이터에서 facts를 계산하는 로직은
    이후 단계). 룰 평가는 C-2.23의 evaluate_conditions를 재사용한다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._version_repo = ScannerRuleVersionRepository(session)
        self._rule_repo = ScannerRuleRepository(session)
        self._candidate_repo = CandidateEventRepository(session)

    async def scan(
        self,
        scanner_rule_version_id: int,
        symbol_facts: dict[str, dict[str, Any]],
        triggered_at: datetime | None = None,
        context_snapshot_id: int | None = None,
        macro: dict | None = None,
        semis_symbols: set[str] | None = None,
    ) -> ScanResult:
        """룰 버전의 조건을 각 종목 facts에 대해 평가하고, 매칭된 종목을 기록한다.

        symbol_facts 예: {"005930": {"volume_ratio": 2.1, "price_change_pct": 5.3}, ...}
        macro가 주어지면 후보 점수를 매크로 레짐으로 조정한다(C-2.63): risk_off면 하향,
        반도체 강세 + 반도체 테마 종목이면 가산.
        """
        version = await self._version_repo.get(scanner_rule_version_id)
        if version is None:
            raise ScannerRuleVersionNotFoundError(scanner_rule_version_id)

        rule = await self._rule_repo.get(version.scanner_rule_id)
        market = rule.market if rule is not None else MarketCode.KR
        regime = (macro or {}).get("regime")
        semis_strength = (macro or {}).get("semis_strength")
        semis_symbols = semis_symbols or set()

        candidates: list[CandidateEvent] = []
        for symbol_code, facts in symbol_facts.items():
            result = evaluate_conditions(version.conditions, facts)
            if not result.matched:
                continue
            score = result.score
            if macro:
                adjusted = macro_score_adjustment(
                    score, regime, semis_strength, symbol_code in semis_symbols
                )
                if adjusted != score:
                    facts = {**facts, "_base_score": score, "_macro_regime": regime}
                score = adjusted
            extra: dict[str, Any] = {}
            if triggered_at is not None:
                extra["triggered_at"] = triggered_at
            candidate = await self._candidate_repo.create(
                scanner_rule_version_id=scanner_rule_version_id,
                market=market,
                symbol_code=symbol_code,
                score=score,
                matched_conditions=result.matched_conditions,
                facts=facts,
                context_snapshot_id=context_snapshot_id,
                **extra,
            )
            candidates.append(candidate)

        await self._session.commit()
        return ScanResult(
            scanner_rule_version_id=scanner_rule_version_id,
            scanned=len(symbol_facts),
            matched=len(candidates),
            candidates=candidates,
        )

    async def list_candidates(
        self,
        scanner_rule_version_id: int | None = None,
        symbol_code: str | None = None,
        market: MarketCode | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CandidateEvent]:
        return await self._candidate_repo.list_filtered(
            scanner_rule_version_id=scanner_rule_version_id,
            symbol_code=symbol_code,
            market=market,
            limit=limit,
            offset=offset,
        )
