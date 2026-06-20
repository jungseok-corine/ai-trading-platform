"""DB 조회 및 수정 함수.

각 함수는 dry_run=True(기본값)이면 로그만 출력하고 DB를 수정하지 않는다.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import PositionEventType, RiskEventResult, StrategyVersionStatus
from app.domain.models.position import Position
from app.domain.models.position_event import PositionEvent
from app.domain.models.risk import RiskEvent
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.watchlist import WatchlistSymbol
from app.maintenance.checks import (
    AccountInput,
    NullRiskEventInput,
    PositionMismatchInput,
    StrategyVersionInput,
)
from app.services.position_service import PositionService

log = logging.getLogger(__name__)


async def fetch_null_risk_event_inputs(session: AsyncSession) -> list[NullRiskEventInput]:
    result = await session.execute(
        select(RiskEvent).where(
            (RiskEvent.rule_name.is_(None)) | (RiskEvent.reason.is_(None))
        )
    )
    return [
        NullRiskEventInput(
            id=e.id,
            result=e.result.value,
            rule_name=e.rule_name,
            reason=e.reason,
        )
        for e in result.scalars().all()
    ]


async def fetch_position_mismatch_inputs(session: AsyncSession) -> list[PositionMismatchInput]:
    accounts = (await session.execute(select(Account))).scalars().all()
    result: list[PositionMismatchInput] = []
    for account in accounts:
        service = PositionService(session)
        for m in await service.diagnose_position_mismatch(account.id):
            result.append(
                PositionMismatchInput(
                    position_id=m.position_id,
                    symbol_code=m.symbol_code,
                    account_id=m.account_id,
                    position_quantity=m.position_quantity,
                    event_quantity_sum=m.event_quantity_sum,
                )
            )
    return result


async def fetch_active_strategy_version_inputs(
    session: AsyncSession,
) -> list[StrategyVersionInput]:
    result = await session.execute(
        select(StrategyVersion, Strategy.name)
        .join(Strategy, Strategy.id == StrategyVersion.strategy_id)
        .where(
            StrategyVersion.status.in_(
                [StrategyVersionStatus.ACTIVE, StrategyVersionStatus.TESTING]
            )
        )
    )
    return [
        StrategyVersionInput(
            id=sv.id,
            strategy_id=sv.strategy_id,
            strategy_name=strategy_name,
            symbol_code=sv.parameters.get("symbol_code"),
            status=sv.status.value,
            parameters=sv.parameters,
        )
        for sv, strategy_name in result.all()
    ]


async def fetch_watchlist_symbol_codes(session: AsyncSession) -> set[str]:
    result = await session.execute(select(WatchlistSymbol.symbol_code))
    return set(result.scalars().all())


async def fetch_account_inputs(session: AsyncSession) -> list[AccountInput]:
    accounts = (await session.execute(select(Account))).scalars().all()
    return [
        AccountInput(
            id=a.id,
            alias=a.alias,
            broker_account_no=a.broker_account_no,
            account_type=a.account_type.value,
        )
        for a in accounts
    ]


async def apply_null_risk_event_fix(
    session: AsyncSession,
    event_ids: list[int],
    dry_run: bool = True,
) -> None:
    """APPROVED risk_events의 NULL rule_name/reason을 기본값으로 채운다.

    REJECTED 이벤트는 손대지 않는다.
    """
    if not event_ids:
        return
    result = await session.execute(
        select(RiskEvent).where(
            RiskEvent.id.in_(event_ids),
            RiskEvent.result == RiskEventResult.APPROVED,
        )
    )
    for e in result.scalars().all():
        before = {"rule_name": e.rule_name, "reason": e.reason}
        if not dry_run:
            e.rule_name = e.rule_name or "all_rules_passed"
            e.reason = e.reason or "Order passed all risk checks"
            session.add(e)
        after = {"rule_name": e.rule_name, "reason": e.reason}
        tag = " [dry-run]" if dry_run else ""
        log.info("risk_event #%d: %s -> %s%s", e.id, before, after, tag)


async def apply_position_mismatch_adjustment(
    session: AsyncSession,
    mismatches: list[PositionMismatchInput],
    dry_run: bool = True,
) -> None:
    """position.quantity는 건드리지 않고 ADJUSTMENT 이벤트만 추가한다.

    감사 목적의 기록 추가이며, 실제 포지션 수량은 이미 DB 기준값이 정답이다.
    """
    for m in mismatches:
        discrepancy = m.position_quantity - m.event_quantity_sum
        tag = " [dry-run]" if dry_run else ""
        log.info(
            "position #%d (%s): qty=%d, event_sum=%d, discrepancy=%+d%s",
            m.position_id, m.symbol_code,
            m.position_quantity, m.event_quantity_sum,
            discrepancy, tag,
        )
        if dry_run:
            continue

        position = await session.get(Position, m.position_id)
        if position is None:
            log.warning("position #%d not found, skipping", m.position_id)
            continue

        price = position.last_price if position.last_price is not None else position.avg_entry_price
        event = PositionEvent(
            position_id=m.position_id,
            trade_id=None,
            event_type=PositionEventType.ADJUSTMENT,
            quantity_delta=discrepancy,
            price=price,
            realized_pnl_delta=None,
            realized_pnl_delta_net=None,
            commission=None,
            tax=None,
            before_quantity=m.event_quantity_sum,
            after_quantity=m.position_quantity,
            before_avg_entry_price=position.avg_entry_price,
            after_avg_entry_price=position.avg_entry_price,
            raw={"source": "maintenance_adjustment", "discrepancy": discrepancy},
        )
        session.add(event)


async def apply_orphan_strategy_version_disable(
    session: AsyncSession,
    version_ids: list[int],
    dry_run: bool = True,
) -> None:
    """orphan 전략 버전의 parameters.enabled를 False로 설정한다."""
    if not version_ids:
        return
    result = await session.execute(
        select(StrategyVersion).where(StrategyVersion.id.in_(version_ids))
    )
    for v in result.scalars().all():
        before = v.parameters.get("enabled", True)
        tag = " [dry-run]" if dry_run else ""
        log.info(
            "strategy_version #%d parameters.enabled: %s -> False%s",
            v.id, before, tag,
        )
        if not dry_run:
            v.parameters = {**v.parameters, "enabled": False}
            session.add(v)
