"""maintenance/runner.py DB 통합 테스트."""
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import (
    AccountType,
    PositionEventType,
    RiskEventResult,
    StrategyVersionStatus,
)
from app.domain.models.position_event import PositionEvent
from app.domain.models.risk import RiskEvent
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.watchlist import Watchlist, WatchlistSymbol
from app.maintenance.runner import run_maintenance
from app.services.position_service import PositionService


async def _create_paper_account(session: AsyncSession, no: str = "00000000-01") -> Account:
    account = Account(account_type=AccountType.PAPER, broker_account_no=no)
    session.add(account)
    await session.flush()
    return account


async def _create_risk_event(
    session: AsyncSession,
    account_id: int,
    result: RiskEventResult,
    rule_name: str | None,
    reason: str | None,
) -> RiskEvent:
    e = RiskEvent(
        account_id=account_id,
        strategy_version_id=None,
        signal_snapshot={},
        context_snapshot={},
        result=result,
        rule_name=rule_name,
        reason=reason,
    )
    session.add(e)
    await session.flush()
    return e


# ---------------------------------------------------------------------------
# 1. dry-run은 DB를 수정하지 않는다
# ---------------------------------------------------------------------------


async def test_dry_run_does_not_modify_db(db_session: AsyncSession) -> None:
    account = await _create_paper_account(db_session)
    risk_event = await _create_risk_event(
        db_session, account.id, RiskEventResult.APPROVED, None, None
    )

    await run_maintenance(db_session, dry_run=True)

    await db_session.refresh(risk_event)
    assert risk_event.rule_name is None
    assert risk_event.reason is None


# ---------------------------------------------------------------------------
# 2. apply: NULL approved risk_event 수정
# ---------------------------------------------------------------------------


async def test_apply_fixes_null_approved_risk_event(db_session: AsyncSession) -> None:
    account = await _create_paper_account(db_session)
    risk_event = await _create_risk_event(
        db_session, account.id, RiskEventResult.APPROVED, None, None
    )

    report = await run_maintenance(db_session, dry_run=False)

    await db_session.refresh(risk_event)
    assert risk_event.rule_name == "all_rules_passed"
    assert risk_event.reason == "Order passed all risk checks"
    assert report.applied.get("null_risk_events") == 1


# ---------------------------------------------------------------------------
# 3. apply: REJECTED NULL risk_event는 수정하지 않는다
# ---------------------------------------------------------------------------


async def test_apply_does_not_fix_rejected_null_risk_event(db_session: AsyncSession) -> None:
    account = await _create_paper_account(db_session)
    risk_event = await _create_risk_event(
        db_session, account.id, RiskEventResult.REJECTED, None, None
    )

    await run_maintenance(db_session, dry_run=False)

    await db_session.refresh(risk_event)
    assert risk_event.rule_name is None
    assert risk_event.reason is None


# ---------------------------------------------------------------------------
# 4. apply: position 불일치 시 ADJUSTMENT 이벤트 추가
# ---------------------------------------------------------------------------


async def test_apply_position_mismatch_adds_adjustment_event(db_session: AsyncSession) -> None:
    account = await _create_paper_account(db_session)
    service = PositionService(db_session)

    # 정상 체결로 포지션 생성 (quantity=10, event_sum=10)
    position = await service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        side=__import__("app.domain.models.enums", fromlist=["TradeSide"]).TradeSide.BUY,
        quantity=10,
        price=Decimal("70000"),
    )

    # 직접 수정으로 불일치 유발 (quantity=12, event_sum=10 → discrepancy=+2)
    position.quantity = 12
    db_session.add(position)
    await db_session.flush()

    report = await run_maintenance(db_session, dry_run=False)

    # ADJUSTMENT 이벤트가 추가되었는지 확인
    events = (
        (
            await db_session.execute(
                select(PositionEvent).where(
                    PositionEvent.position_id == position.id,
                    PositionEvent.event_type == PositionEventType.ADJUSTMENT,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    adj = events[0]
    assert adj.quantity_delta == 2
    assert adj.before_quantity == 10
    assert adj.after_quantity == 12
    assert adj.raw["source"] == "maintenance_adjustment"
    assert report.applied.get("position_mismatches") == 1


# ---------------------------------------------------------------------------
# 5. apply: orphan strategy_version 비활성화
# ---------------------------------------------------------------------------


async def test_apply_disables_orphan_strategy_version(db_session: AsyncSession) -> None:
    strategy = Strategy(name="NAVER_MA")
    db_session.add(strategy)
    await db_session.flush()

    version = StrategyVersion(
        strategy_id=strategy.id,
        version_no=1,
        parameters={"symbol_code": "035420"},
        status=StrategyVersionStatus.ACTIVE,
    )
    db_session.add(version)
    await db_session.flush()

    # watchlist에는 035420 없음
    watchlist = Watchlist(name="test_watchlist")
    db_session.add(watchlist)
    await db_session.flush()
    db_session.add(WatchlistSymbol(watchlist_id=watchlist.id, symbol_code="005930"))
    await db_session.flush()

    report = await run_maintenance(db_session, dry_run=False)

    await db_session.refresh(version)
    assert version.parameters.get("enabled") is False
    assert report.applied.get("orphan_strategy_versions") == 1


# ---------------------------------------------------------------------------
# 6. placeholder 계정: 탐지되지만 자동 수정 없음
# ---------------------------------------------------------------------------


async def test_placeholder_account_detected_but_not_auto_fixed(db_session: AsyncSession) -> None:
    placeholder = Account(
        account_type=AccountType.PAPER,
        broker_account_no="너의모의계좌번호",
    )
    db_session.add(placeholder)
    await db_session.flush()

    report = await run_maintenance(db_session, dry_run=False)

    placeholder_findings = [
        f for f in report.findings if f.check_name == "placeholder_account"
    ]
    assert len(placeholder_findings) == 1
    assert placeholder_findings[0].auto_fixable is False

    # DB에서도 값이 그대로여야 한다
    await db_session.refresh(placeholder)
    assert placeholder.broker_account_no == "너의모의계좌번호"


# ---------------------------------------------------------------------------
# 7. 문제 없는 DB: findings 0건
# ---------------------------------------------------------------------------


async def test_clean_db_has_no_findings(db_session: AsyncSession) -> None:
    # 깨끗한 계정만 생성 (정상 계좌번호)
    account = await _create_paper_account(db_session, "12345678-01")
    # rule_name/reason 있는 정상 risk_event
    await _create_risk_event(
        db_session, account.id, RiskEventResult.APPROVED, "all_rules_passed", "ok"
    )

    report = await run_maintenance(db_session, dry_run=True)

    assert report.total_findings == 0


# ---------------------------------------------------------------------------
# 8. dry-run report: auto_fixable_count 프로퍼티
# ---------------------------------------------------------------------------


async def test_report_auto_fixable_count(db_session: AsyncSession) -> None:
    account = await _create_paper_account(db_session)
    # approved NULL (auto_fixable=True)
    await _create_risk_event(db_session, account.id, RiskEventResult.APPROVED, None, None)
    # rejected NULL (auto_fixable=False)
    await _create_risk_event(db_session, account.id, RiskEventResult.REJECTED, None, None)
    # placeholder account (auto_fixable=False)
    db_session.add(Account(account_type=AccountType.PAPER, broker_account_no="PLACEHOLDER"))
    await db_session.flush()

    report = await run_maintenance(db_session, dry_run=True)

    assert report.total_findings == 3
    assert report.auto_fixable_count == 1
