"""C-3.2 연구 루프 제안 퍼널 집계 테스트."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import ProposalStatus
from app.domain.models.scanner import ScannerRule, ScannerRuleVersion
from app.domain.models.scanner_proposal import ScannerRuleProposal
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.strategy_proposal import StrategyProposal
from app.services.proposal_funnel_service import ProposalFunnelService


async def _setup(session: AsyncSession):
    strat = Strategy(name="FunnelStrat", description="t")
    session.add(strat)
    await session.flush()
    sv = StrategyVersion(
        strategy_id=strat.id, version_no=1,
        parameters={"strategy_type": "moving_average_cross", "symbol_code": "005930"},
    )
    rule = ScannerRule(name="FunnelRule")
    session.add_all([sv, rule])
    await session.flush()
    rv = ScannerRuleVersion(scanner_rule_id=rule.id, version_no=1, conditions=[])
    session.add(rv)
    await session.flush()
    return strat, sv, rule, rv


def _sp(strat_id, status, version_id=None):
    return StrategyProposal(
        strategy_id=strat_id, title="t", suggested_parameters={"x": 1},
        status=status, created_version_id=version_id,
    )


def _scp(rule_id, status, version_id=None):
    return ScannerRuleProposal(
        scanner_rule_id=rule_id, title="t", suggested_conditions=[],
        status=status, created_version_id=version_id,
    )


async def test_funnel_counts_stages(db_session: AsyncSession) -> None:
    strat, sv, rule, rv = await _setup(db_session)
    db_session.add_all([
        _sp(strat.id, ProposalStatus.PENDING),
        _sp(strat.id, ProposalStatus.APPROVED, sv.id),   # 버전 생성됨
        _sp(strat.id, ProposalStatus.APPROVED, None),    # 승인됐지만 버전 없음
        _sp(strat.id, ProposalStatus.REJECTED),
        _scp(rule.id, ProposalStatus.PENDING),
        _scp(rule.id, ProposalStatus.APPROVED, rv.id),
    ])
    await db_session.flush()

    out = await ProposalFunnelService(db_session).funnel(days=30)

    s = out["strategy"]
    assert s["generated"] == 4 and s["pending"] == 1
    assert s["approved"] == 2 and s["rejected"] == 1
    assert s["versions_created"] == 1
    assert s["approval_rate"] == 0.667

    sc = out["scanner"]
    assert sc["generated"] == 2 and sc["approved"] == 1
    assert sc["versions_created"] == 1 and sc["approval_rate"] == 1.0

    c = out["combined"]
    assert c["generated"] == 6 and c["approved"] == 3 and c["versions_created"] == 2
    assert c["approval_rate"] == 0.75
    assert "retrospective" in out


async def test_funnel_window_excludes_old(db_session: AsyncSession) -> None:
    strat, sv, rule, rv = await _setup(db_session)
    old = _sp(strat.id, ProposalStatus.APPROVED, sv.id)
    db_session.add(old)
    await db_session.flush()
    old.created_at = datetime.now(timezone.utc) - timedelta(days=40)
    await db_session.flush()

    out = await ProposalFunnelService(db_session).funnel(days=30)
    assert out["strategy"]["generated"] == 0
    assert out["strategy"]["approval_rate"] is None
