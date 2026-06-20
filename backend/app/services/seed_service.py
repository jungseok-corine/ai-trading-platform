from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import (
    MarketCode,
    ScannerRuleStatus,
    StrategyVersionStatus,
)
from app.services.assignment_service import AssignmentService
from app.services.scanner_service import ScannerService
from app.services.strategy_service import StrategyService

# 모든 시드는 [예시] 접두사로 멱등성을 보장하고 사람이 식별하기 쉽게 한다.
PREFIX = "[예시]"

# 안전: 시드 전략은 모두 auto_trade_enabled=False, status=TESTING (실거래/자동매매 없음).
_BASE = {"timeframe": "5m", "quantity": 1, "auto_trade_enabled": False}

_SCANNER_RULES = [
    {"name": f"{PREFIX} 거래량 급증",
     "conditions": [{"type": "volume_spike", "params": {"multiplier": 2.0}}]},
    {"name": f"{PREFIX} 거래량 급증 + 상승",
     "conditions": [{"type": "volume_spike", "params": {"multiplier": 2.0}},
                    {"type": "price_change_pct", "params": {"min_pct": 3.0}}]},
    {"name": f"{PREFIX} 회전율 상위 + 거래량",
     "conditions": [{"type": "turnover_rank", "params": {"max_rank": 50}},
                    {"type": "volume_spike", "params": {"multiplier": 1.5}}]},
]

_STRATEGIES = [
    {"name": f"{PREFIX} MA 5/20",
     "params": {**_BASE, "strategy_type": "moving_average_cross",
                "short_window": 5, "long_window": 20}},
    {"name": f"{PREFIX} MA 10/60",
     "params": {**_BASE, "strategy_type": "moving_average_cross",
                "short_window": 10, "long_window": 60}},
    {"name": f"{PREFIX} 거래량확인 MA",
     "params": {**_BASE, "strategy_type": "volume_confirmed_ma_cross",
                "short_window": 5, "long_window": 20, "volume_multiplier": 1.5}},
]

_ASSIGNMENT_RULES = [
    {"name": f"{PREFIX} 거래량급증 → MA", "strategy_type": "moving_average_cross",
     "scanner": f"{PREFIX} 거래량 급증", "priority": 10,
     "default_parameters": {**_BASE, "strategy_type": "moving_average_cross",
                            "short_window": 5, "long_window": 20}},
    {"name": f"{PREFIX} 회전율 → 거래량확인MA", "strategy_type": "volume_confirmed_ma_cross",
     "scanner": f"{PREFIX} 회전율 상위 + 거래량", "priority": 5,
     "default_parameters": {**_BASE, "strategy_type": "volume_confirmed_ma_cross",
                            "short_window": 5, "long_window": 20, "volume_multiplier": 1.5}},
]


@dataclass
class SeedSummary:
    scanners_created: list[str] = field(default_factory=list)
    strategies_created: list[str] = field(default_factory=list)
    assignment_rules_created: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scanners_created": self.scanners_created,
            "strategies_created": self.strategies_created,
            "assignment_rules_created": self.assignment_rules_created,
            "skipped_existing": self.skipped_existing,
        }


class SeedService:
    """연구 루프가 바로 돌아갈 '예시 스캐너 룰 + 전략 + 배정 룰'을 시딩한다 (C-2.58).

    전략·조건이 비어 있으면 파이프라인이 씹을 재료가 없다. 이 헬퍼가 안전한 예시를 채운다.
    멱등([예시] 이름으로 중복 방지). 모든 전략은 auto_trade_enabled=False·status=TESTING이라
    실거래/자동매매가 켜지지 않는다(안전 불변식 유지).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._scanner = ScannerService(session)
        self._strategy = StrategyService(session)
        self._assignment = AssignmentService(session)

    async def seed_examples(self) -> SeedSummary:
        summary = SeedSummary()

        existing_scanners = {r.name: r for r, _ in await self._scanner.list_rules()}
        for spec in _SCANNER_RULES:
            if spec["name"] in existing_scanners:
                summary.skipped_existing.append(spec["name"])
                continue
            rule = await self._scanner.create_rule(spec["name"], description="시드 예시")
            await self._scanner.create_version(
                rule.id, conditions=spec["conditions"],
                change_description="시드 초기 버전", status=ScannerRuleStatus.TESTING,
            )
            existing_scanners[spec["name"]] = rule
            summary.scanners_created.append(spec["name"])

        existing_strategies = {s.name for s, _ in await self._strategy.list_strategies()}
        for spec in _STRATEGIES:
            if spec["name"] in existing_strategies:
                summary.skipped_existing.append(spec["name"])
                continue
            strategy = await self._strategy.create_strategy(spec["name"], description="시드 예시")
            await self._strategy.create_version(
                strategy.id, parameters=spec["params"],
                change_description="시드 초기 버전", status=StrategyVersionStatus.TESTING,
            )
            summary.strategies_created.append(spec["name"])

        existing_assign = {r.name for r in await self._assignment.list_rules()}
        for spec in _ASSIGNMENT_RULES:
            if spec["name"] in existing_assign:
                summary.skipped_existing.append(spec["name"])
                continue
            scanner_rule = existing_scanners.get(spec["scanner"])
            await self._assignment.create_rule(
                name=spec["name"], strategy_type=spec["strategy_type"],
                market=MarketCode.KR,
                scanner_rule_id=scanner_rule.id if scanner_rule else None,
                default_parameters=spec["default_parameters"], priority=spec["priority"],
                description="시드 예시",
            )
            summary.assignment_rules_created.append(spec["name"])

        return summary
