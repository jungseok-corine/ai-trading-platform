"""C-6.7: AI 의사결정 피드 — read-only 타임라인 집계."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import ProposalStatus
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.strategy_proposal import StrategyProposal
from app.services.ai_activity_feed_service import AiActivityFeedService


async def _proposal(
    session: AsyncSession,
    *,
    status: ProposalStatus = ProposalStatus.PENDING,
    reviewed_at: datetime | None = None,
    backtest_summary: dict | None = None,
    created_at: datetime | None = None,
) -> StrategyProposal:
    strategy = Strategy(name="feed test", description="t")
    session.add(strategy)
    await session.flush()
    p = StrategyProposal(
        strategy_id=strategy.id,
        title="feed 제안",
        suggested_parameters={"strategy_type": "moving_average_cross"},
        status=status,
        reviewed_at=reviewed_at,
        backtest_summary=backtest_summary,
    )
    if created_at is not None:
        p.created_at = created_at
    session.add(p)
    await session.commit()
    return p


@pytest.mark.asyncio
async def test_feed_includes_proposal_created_with_backtest_verdict(db_session: AsyncSession):
    await _proposal(db_session, backtest_summary={"verdict": "base_better"})
    feed = await AiActivityFeedService(db_session).feed(days=1)
    created = [e for e in feed["events"] if e["kind"] == "proposal_created"]
    assert created
    assert "base_better" in created[0]["detail"]


@pytest.mark.asyncio
async def test_feed_includes_review_events(db_session: AsyncSession):
    now = datetime.now(timezone.utc)
    await _proposal(
        db_session,
        status=ProposalStatus.APPROVED,
        reviewed_at=now,
        created_at=now - timedelta(days=10),  # 생성은 윈도우 밖, 검토는 안
    )
    feed = await AiActivityFeedService(db_session).feed(days=1)
    kinds = {e["kind"] for e in feed["events"]}
    assert "proposal_approved" in kinds
    assert "proposal_created" not in kinds  # 생성 이벤트는 윈도우 밖


@pytest.mark.asyncio
async def test_feed_sorted_desc_and_limited(db_session: AsyncSession):
    for _ in range(3):
        await _proposal(db_session)
    feed = await AiActivityFeedService(db_session).feed(days=1, limit=2)
    assert feed["count"] == 2
    ts = [e["ts"] for e in feed["events"]]
    assert ts == sorted(ts, reverse=True)


@pytest.mark.asyncio
async def test_feed_empty_window(db_session: AsyncSession):
    feed = await AiActivityFeedService(db_session).feed(days=1)
    assert feed["events"] == []
    assert feed["count"] == 0
