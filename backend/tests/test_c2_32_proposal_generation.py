"""C-2.32 AI Proposal Generation 테스트."""

from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, TradeSide
from app.domain.models.trade import Trade
from app.main import app
from app.services.proposal_generator import suggest_parameter_change
from app.services.strategy_service import StrategyService
from app.trading.experiment.metrics import compute_metrics


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


# --- 순수 휴리스틱 ------------------------------------------------------------
def test_suggest_volume_strategy_when_losing() -> None:
    metrics = compute_metrics([Decimal("-10")] * 6)  # 기대값 음수, 6건
    s = suggest_parameter_change(
        "volume_confirmed_ma_cross",
        {"strategy_type": "volume_confirmed_ma_cross", "volume_multiplier": 1.5},
        metrics,
    )
    assert s is not None
    assert s.suggested_parameters["volume_multiplier"] == 2.0  # 1.5 * 1.3 = 1.95 → 2.0
    assert "기대값" in s.rationale


def test_suggest_ma_strategy_widens_long_window() -> None:
    metrics = compute_metrics([Decimal("-5")] * 6)
    s = suggest_parameter_change(
        "moving_average_cross",
        {"strategy_type": "moving_average_cross", "long_window": 20},
        metrics,
    )
    assert s is not None
    assert s.suggested_parameters["long_window"] == 25


def test_no_suggestion_when_profitable_or_insufficient() -> None:
    profitable = compute_metrics([Decimal("10")] * 6)
    assert suggest_parameter_change(
        "volume_confirmed_ma_cross", {"volume_multiplier": 1.5}, profitable
    ) is None

    too_few = compute_metrics([Decimal("-10")] * 2)
    assert suggest_parameter_change(
        "volume_confirmed_ma_cross", {"volume_multiplier": 1.5}, too_few
    ) is None


# --- DB 통합 ------------------------------------------------------------------
async def _seed_version(session: AsyncSession, params: dict, pnls: list[str]) -> tuple[int, int]:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000")
    session.add(account)
    await session.commit()
    svc = StrategyService(session)
    strategy = await svc.create_strategy("gen-target")
    version = await svc.create_version(strategy.id, parameters=params)
    for p in pnls:
        session.add(
            Trade(account_id=account.id, strategy_version_id=version.id, symbol_code="005930",
                  side=TradeSide.BUY, quantity=1, pnl_amount=Decimal(p),
                  order_status=OrderStatus.FILLED)
        )
    await session.commit()
    return strategy.id, version.id


async def test_generate_creates_pending_proposal(db_session: AsyncSession) -> None:
    strategy_id, version_id = await _seed_version(
        db_session,
        {"strategy_type": "volume_confirmed_ma_cross", "symbol_code": "005930", "volume_multiplier": 1.5},
        ["-10", "-20", "-5", "30", "-15", "-8"],  # 기대값 음수
    )
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            gen = await client.post(
                "/api/v1/strategy-proposals/generate",
                json={"strategy_id": strategy_id, "version_id": version_id},
            )
            assert gen.status_code == 200
            body = gen.json()
            assert body["status"] == "pending"
            assert body["source"] == "ai"
            assert body["base_version_id"] == version_id
            assert body["suggested_parameters"]["volume_multiplier"] == 2.0

            # 목록에 pending 제안으로 잡힘
            listing = await client.get(
                "/api/v1/strategy-proposals", params={"strategy_id": strategy_id}
            )
            assert len(listing.json()) == 1
    finally:
        app.dependency_overrides.clear()


async def test_generate_returns_204_when_no_change(db_session: AsyncSession) -> None:
    strategy_id, version_id = await _seed_version(
        db_session,
        {"strategy_type": "volume_confirmed_ma_cross", "symbol_code": "005930", "volume_multiplier": 1.5},
        ["10", "20", "5", "30", "15", "8"],  # 기대값 양수 → 제안 없음
    )
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            gen = await client.post(
                "/api/v1/strategy-proposals/generate",
                json={"strategy_id": strategy_id, "version_id": version_id},
            )
            assert gen.status_code == 204
    finally:
        app.dependency_overrides.clear()


async def test_generate_unknown_version_404(db_session: AsyncSession) -> None:
    strategy_id, _ = await _seed_version(
        db_session, {"strategy_type": "moving_average_cross", "symbol_code": "005930"}, []
    )
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            gen = await client.post(
                "/api/v1/strategy-proposals/generate",
                json={"strategy_id": strategy_id, "version_id": 999999},
            )
            assert gen.status_code == 404
    finally:
        app.dependency_overrides.clear()
