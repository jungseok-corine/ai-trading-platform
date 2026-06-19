"""C-2.45 제안 일괄 검토(bulk approve/reject) 테스트."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import ProposalStatus, ScannerRuleStatus
from app.main import app
from app.services.scanner_proposal_service import ScannerProposalService
from app.services.scanner_service import ScannerService


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _make_proposal(session: AsyncSession, name: str) -> int:
    scanner = ScannerService(session)
    rule = await scanner.create_rule(name)
    sv = await scanner.create_version(
        rule.id, conditions=[{"type": "volume_spike", "params": {"multiplier": 2.0}}],
        status=ScannerRuleStatus.TESTING,
    )
    proposal = await ScannerProposalService(session).create_proposal(
        scanner_rule_id=rule.id,
        suggested_conditions=[{"type": "volume_spike", "params": {"multiplier": 2.6}}],
        title="강화", base_version_id=sv.id,
    )
    return proposal.id


async def test_bulk_approve_creates_versions(db_session: AsyncSession) -> None:
    ids = [await _make_proposal(db_session, f"R{i}") for i in range(3)]
    service = ScannerProposalService(db_session)
    result = await service.bulk_review(ids, "approve", reviewed_by="user")

    assert result["action"] == "approve"
    assert set(result["succeeded"]) == set(ids)
    assert result["failed"] == []
    remaining = await service.list_proposals(status=ProposalStatus.PENDING)
    assert remaining == []


async def test_bulk_reject(db_session: AsyncSession) -> None:
    ids = [await _make_proposal(db_session, f"R{i}") for i in range(2)]
    service = ScannerProposalService(db_session)
    result = await service.bulk_review(ids, "reject")
    assert set(result["succeeded"]) == set(ids)
    rejected = await service.list_proposals(status=ProposalStatus.REJECTED)
    assert len(rejected) == 2


async def test_bulk_isolates_failures(db_session: AsyncSession) -> None:
    pid = await _make_proposal(db_session, "R0")
    service = ScannerProposalService(db_session)
    await service.reject(pid)  # 이미 검토됨

    result = await service.bulk_review([pid, 99999], "approve")
    assert result["succeeded"] == []
    reasons = {f["id"]: f["reason"] for f in result["failed"]}
    assert reasons[pid] == "already reviewed"
    assert reasons[99999] == "not found"


async def test_bulk_invalid_action_raises(db_session: AsyncSession) -> None:
    service = ScannerProposalService(db_session)
    import pytest

    with pytest.raises(ValueError):
        await service.bulk_review([], "delete")


async def test_bulk_review_via_api(db_session: AsyncSession) -> None:
    ids = [await _make_proposal(db_session, f"R{i}") for i in range(2)]
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/scanner-proposals/bulk-review",
                json={"proposal_ids": ids, "action": "approve", "reviewed_by": "user"},
            )
            assert resp.status_code == 200
            assert set(resp.json()["succeeded"]) == set(ids)

            bad = await client.post(
                "/api/v1/scanner-proposals/bulk-review",
                json={"proposal_ids": ids, "action": "delete"},
            )
            assert bad.status_code == 422
    finally:
        app.dependency_overrides.clear()
