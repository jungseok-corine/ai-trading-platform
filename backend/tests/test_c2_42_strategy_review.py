"""C-2.42 전략 버전 자동 점검 테스트."""

from decimal import Decimal
from zoneinfo import ZoneInfo

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.account import Account
from app.domain.models.enums import (
    AccountType,
    OrderStatus,
    ProposalStatus,
    StrategyVersionStatus,
    TradeSide,
)
from app.domain.models.trade import Trade
from app.main import app
from app.services.proposal_service import ProposalService
from app.services.strategy_review_service import StrategyReviewService
from app.services.strategy_service import StrategyService

KST = ZoneInfo("Asia/Seoul")


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _seed_losing_version(
    session: AsyncSession, name: str, status=StrategyVersionStatus.TESTING
) -> int:
    """기대값이 음수인(6건 손실) active 전략 버전을 만든다."""
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000")
    session.add(account)
    await session.commit()
    svc = StrategyService(session)
    strategy = await svc.create_strategy(name)
    version = await svc.create_version(
        strategy.id,
        parameters={"strategy_type": "volume_confirmed_ma_cross", "volume_multiplier": 1.5},
        status=status,
    )
    for _ in range(6):
        session.add(
            Trade(account_id=account.id, strategy_version_id=version.id, symbol_code="005930",
                  side=TradeSide.BUY, quantity=1, pnl_amount=Decimal("-10"),
                  order_status=OrderStatus.FILLED)
        )
    await session.commit()
    return version.id


async def test_review_generates_proposals_for_losing_versions(db_session: AsyncSession) -> None:
    await _seed_losing_version(db_session, "AAA")
    summary = await StrategyReviewService(db_session).review()
    assert summary.versions_reviewed == 1
    assert summary.proposals_created == 1
    assert summary.skipped_existing == 0


async def test_review_skips_versions_with_existing_pending(db_session: AsyncSession) -> None:
    service = StrategyReviewService(db_session)
    await _seed_losing_version(db_session, "AAA")
    first = await service.review()
    assert first.proposals_created == 1
    second = await service.review()
    assert second.proposals_created == 0
    assert second.skipped_existing == 1


async def test_review_skips_profitable_versions(db_session: AsyncSession) -> None:
    # 수익 전략은 제안 대상이 아니다(C-2.32: 기대값 양수면 제안 없음).
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000")
    db_session.add(account)
    await db_session.commit()
    svc = StrategyService(db_session)
    strategy = await svc.create_strategy("WIN")
    version = await svc.create_version(
        strategy.id,
        parameters={"strategy_type": "volume_confirmed_ma_cross", "volume_multiplier": 1.5},
        status=StrategyVersionStatus.TESTING,
    )
    for _ in range(6):
        db_session.add(
            Trade(account_id=account.id, strategy_version_id=version.id, symbol_code="005930",
                  side=TradeSide.BUY, quantity=1, pnl_amount=Decimal("10"),
                  order_status=OrderStatus.FILLED)
        )
    await db_session.commit()

    summary = await StrategyReviewService(db_session).review()
    assert summary.versions_reviewed == 1
    assert summary.proposals_created == 0


async def test_review_records_run(db_session: AsyncSession) -> None:
    await _seed_losing_version(db_session, "AAA")
    service = StrategyReviewService(db_session)
    await service.review_and_record()
    runs = await service.list_runs()
    assert len(runs) == 1
    assert runs[0].job_id == "strategy_review"
    assert runs[0].summary["proposals_created"] == 1


async def test_review_via_api(db_session: AsyncSession) -> None:
    await _seed_losing_version(db_session, "AAA")
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            run = await client.post("/api/v1/strategy-review/run")
            assert run.status_code == 201
            assert run.json()["proposals_created"] == 1

            runs = await client.get("/api/v1/strategy-review/runs")
            assert runs.status_code == 200
            assert len(runs.json()) == 1

            pending = await ProposalService(db_session).list_proposals(
                status=ProposalStatus.PENDING
            )
            assert len(pending) == 1
    finally:
        app.dependency_overrides.clear()
