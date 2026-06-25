"""Action Inbox v1 (read-only 집계) 테스트."""
from datetime import datetime, timedelta, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.enums import ProposalStatus
from app.domain.models.scanner import ScannerRule, ScannerRuleVersion
from app.domain.models.strategy import Strategy
from app.domain.models.strategy_proposal import StrategyProposal
from app.main import app
from app.services.action_inbox_service import ActionInboxService


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _seed_scanner_version(session: AsyncSession) -> int:
    rule = ScannerRule(name="InboxScanRule")
    session.add(rule)
    await session.flush()
    rv = ScannerRuleVersion(scanner_rule_id=rule.id, version_no=1, conditions=[])
    session.add(rv)
    await session.flush()
    return rv.id


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


async def test_inbox_surfaces_recent_high_score_candidate(db_session: AsyncSession) -> None:
    rv_id = await _seed_scanner_version(db_session)
    now = datetime.now(timezone.utc)
    db_session.add(CandidateEvent(
        scanner_rule_version_id=rv_id, symbol_code="005930",
        triggered_at=now - timedelta(hours=1), score=85,
        matched_conditions=["volume_spike", "price_change_pct"],
    ))
    await db_session.flush()

    out = await ActionInboxService(db_session).items()
    cand = [i for i in out["items"] if i["type"] == "candidate_event"]
    assert len(cand) == 1
    item = cand[0]
    assert item["title"] == "후보 종목 발견: 005930"
    assert item["description"] == "점수 85, 조건 2개"
    assert item["severity"] == "attention"
    assert item["source"] == "candidate_events"
    assert item["related_url"] == "research:candidates"
    assert item["dismissible"] is False


async def test_inbox_ignores_old_candidates(db_session: AsyncSession) -> None:
    rv_id = await _seed_scanner_version(db_session)
    now = datetime.now(timezone.utc)
    db_session.add(CandidateEvent(
        scanner_rule_version_id=rv_id, symbol_code="000660",
        triggered_at=now - timedelta(hours=48), score=90,
        matched_conditions=["volume_spike"],
    ))
    await db_session.flush()

    out = await ActionInboxService(db_session).items()
    assert not any(i["type"] == "candidate_event" for i in out["items"])


async def test_inbox_caps_candidate_items(db_session: AsyncSession) -> None:
    rv_id = await _seed_scanner_version(db_session)
    now = datetime.now(timezone.utc)
    for n in range(8):
        db_session.add(CandidateEvent(
            scanner_rule_version_id=rv_id, symbol_code=f"00{n:04d}",
            triggered_at=now - timedelta(minutes=n + 1), score=80,
            matched_conditions=["volume_spike"],
        ))
    await db_session.flush()

    out = await ActionInboxService(db_session).items()
    cand = [i for i in out["items"] if i["type"] == "candidate_event"]
    assert len(cand) == 5  # 최대 노출 캡


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
