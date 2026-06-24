"""Action Inbox v1 (read-only 집계) 테스트."""
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import ProposalStatus
from app.domain.models.strategy import Strategy
from app.domain.models.strategy_proposal import StrategyProposal
from app.main import app
from app.services.action_inbox_service import ActionInboxService


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def test_inbox_empty_has_no_items(db_session: AsyncSession) -> None:
    out = await ActionInboxService(db_session).items()
    assert out["counts"]["total"] == 0
    assert out["items"] == []
    assert "generated_at" in out


async def test_inbox_flags_pending_strategy_proposals(db_session: AsyncSession) -> None:
    strat = Strategy(name="InboxStrat", description="t")
    db_session.add(strat)
    await db_session.flush()
    db_session.add(StrategyProposal(
        strategy_id=strat.id, title="개선안", suggested_parameters={"x": 1},
        status=ProposalStatus.PENDING,
    ))
    await db_session.flush()

    out = await ActionInboxService(db_session).items()
    ids = [i["id"] for i in out["items"]]
    assert "pending_strategy_proposals" in ids
    item = next(i for i in out["items"] if i["id"] == "pending_strategy_proposals")
    assert item["severity"] == "attention"
    assert item["dismissible"] is False  # v1: 조치 버튼 없음
    assert item["type"] == "strategy_proposal"
    assert out["counts"]["attention"] >= 1


async def test_inbox_api_returns_structure(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/action-inbox")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) >= {"generated_at", "counts", "items"}
        assert set(body["counts"].keys()) >= {"alert", "attention", "total"}
    finally:
        app.dependency_overrides.pop(get_db, None)
