import dataclasses
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import RiskEventResult
from app.domain.models.risk import RiskConfig
from app.domain.repositories.risk import RiskConfigRepository, RiskEventRepository
from app.trading.broker.base import BrokerClient
from app.trading.risk.context import RiskContextBuilder
from app.trading.risk.manager import RiskManager
from app.trading.risk.rules import DEFAULT_RULES, RiskCheckResult
from app.trading.strategy.base import Signal


class RiskConfigNotFoundError(Exception):
    """해당 계좌의 risk_configs row가 존재하지 않을 때 발생."""


def _jsonable(value: Any) -> Any:
    """dataclass/Decimal/Enum을 포함한 객체를 JSONB 저장 가능한 형태로 변환한다."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = dataclasses.asdict(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    return value


class RiskService:
    """RiskContext 생성, RiskManager 판정, risk_events 기록을 담당한다."""

    def __init__(self, session: AsyncSession, broker: BrokerClient) -> None:
        self._session = session
        self._risk_config_repo = RiskConfigRepository(session)
        self._risk_event_repo = RiskEventRepository(session)
        self._context_builder = RiskContextBuilder(session, broker)
        self._manager = RiskManager(DEFAULT_RULES)

    async def get_config(self, account_id: int) -> RiskConfig:
        config = await self._risk_config_repo.get_by_account_id(account_id)
        if config is None:
            raise RiskConfigNotFoundError(account_id)
        return config

    async def update_config(self, account_id: int, **fields: Any) -> RiskConfig:
        config = await self.get_config(account_id)
        await self._risk_config_repo.update(config, **fields)
        await self._session.commit()
        return config

    async def set_emergency_stop(self, account_id: int, enabled: bool) -> RiskConfig:
        config = await self.get_config(account_id)
        await self._risk_config_repo.update(config, emergency_stop=enabled)
        await self._risk_event_repo.create(
            account_id=account_id,
            strategy_version_id=None,
            signal_snapshot={"action": "emergency_stop", "enabled": enabled},
            context_snapshot={},
            result=RiskEventResult.APPROVED,
            rule_name="emergency_stop_toggle",
            reason=f"emergency_stop -> {enabled}",
        )
        await self._session.commit()
        return config

    async def validate_signal(self, account_id: int, signal: Signal) -> RiskCheckResult:
        config = await self.get_config(account_id)
        context = await self._context_builder.build(account_id)
        result = self._manager.validate(signal, config, context)

        await self._risk_event_repo.create(
            account_id=account_id,
            strategy_version_id=signal.strategy_version_id,
            signal_snapshot=_jsonable(signal),
            context_snapshot=_jsonable(context),
            result=RiskEventResult.APPROVED if result.approved else RiskEventResult.REJECTED,
            rule_name=result.rule_name if result.rule_name is not None else "all_rules_passed",
            reason=result.reason if result.reason is not None else "Order passed all risk checks",
        )
        await self._session.commit()
        return result
