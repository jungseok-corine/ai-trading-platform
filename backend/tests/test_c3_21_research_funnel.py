"""C-3.21 연구 루프 전반부 퍼널 테스트."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.enums import ExperimentStatus, MarketCode
from app.domain.models.experiment import Experiment
from app.domain.models.scanner import ScannerRule, ScannerRuleVersion
from app.domain.models.strategy_assignment import StrategyAssignmentLog
from app.services.research_funnel_service import ResearchFunnelService


async def test_funnel_counts_and_rate(db_session: AsyncSession) -> None:
    rule = ScannerRule(name="FunnelFront")
    db_session.add(rule)
    await db_session.flush()
    rv = ScannerRuleVersion(scanner_rule_id=rule.id, version_no=1, conditions=[])
    db_session.add(rv)
    await db_session.flush()

    # 후보 2개, 그중 1개만 배정
    c1 = CandidateEvent(scanner_rule_version_id=rv.id, market=MarketCode.KR,
                        symbol_code="005930", triggered_at=datetime.now(timezone.utc), score=80)
    c2 = CandidateEvent(scanner_rule_version_id=rv.id, market=MarketCode.KR,
                        symbol_code="000660", triggered_at=datetime.now(timezone.utc), score=70)
    db_session.add_all([c1, c2])
    await db_session.flush()
    db_session.add(StrategyAssignmentLog(
        candidate_event_id=c1.id, market=MarketCode.KR, symbol_code="005930",
        strategy_type="moving_average_cross",
    ))
    db_session.add(Experiment(market=MarketCode.KR, name="E1", status=ExperimentStatus.RUNNING))
    await db_session.flush()

    out = await ResearchFunnelService(db_session).funnel(days=30)
    assert out["candidates"] == 2
    assert out["assignments"] == 1
    assert out["candidates_assigned"] == 1
    assert out["assignment_rate"] == 0.5
    assert out["experiments"] == 1
    assert out["experiments_running"] == 1


async def test_funnel_empty(db_session: AsyncSession) -> None:
    out = await ResearchFunnelService(db_session).funnel()
    assert out["candidates"] == 0
    assert out["assignment_rate"] is None
