"""C-3.12 리스크 이벤트 요약 테스트."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, RiskEventResult
from app.domain.models.risk import RiskEvent
from app.services.risk_event_summary_service import RiskEventSummaryService


async def _account(session: AsyncSession) -> Account:
    acc = Account(account_type=AccountType.PAPER, broker_account_no="50192525-01")
    session.add(acc)
    await session.flush()
    return acc


def _event(acc_id, result, rule, reason=None):
    return RiskEvent(
        account_id=acc_id, signal_snapshot={}, context_snapshot={},
        result=result, rule_name=rule, reason=reason,
    )


async def test_summary_counts_and_rules(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    db_session.add_all([
        _event(acc.id, RiskEventResult.APPROVED, "max_position_size"),
        _event(acc.id, RiskEventResult.REJECTED, "max_position_size", "한도 초과"),
        _event(acc.id, RiskEventResult.REJECTED, "max_daily_loss", "일손실 한도"),
        _event(acc.id, RiskEventResult.REJECTED, "max_position_size", "한도 초과2"),
    ])
    await db_session.flush()

    out = await RiskEventSummaryService(db_session).summary(days=30)
    assert out["total"] == 4
    assert out["approved"] == 1 and out["rejected"] == 3
    assert out["rejection_rate"] == 75.0
    # 차단 많은 룰이 먼저
    assert out["by_rule"][0]["rule_name"] == "max_position_size"
    assert out["by_rule"][0]["rejected"] == 2
    # 최근 차단 목록
    assert len(out["recent_rejections"]) == 3
    assert all(r["reason"] is not None for r in out["recent_rejections"])


async def test_summary_empty(db_session: AsyncSession) -> None:
    out = await RiskEventSummaryService(db_session).summary()
    assert out["total"] == 0
    assert out["rejection_rate"] is None
