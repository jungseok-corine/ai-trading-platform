"""C-2.30 Paper-to-Live Promotion Gate 테스트."""

from datetime import datetime, timezone
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, TradeSide
from app.domain.models.trade import Trade
from app.main import app
from app.services.strategy_service import StrategyService


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _seed_version_with_trades(session: AsyncSession) -> int:
    """pnl [100, -40, 60], 1일~5일에 걸친 체결을 가진 전략 버전을 만든다."""
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000")
    session.add(account)
    await session.commit()

    version = await StrategyService(session).create_version(
        (await StrategyService(session).create_strategy("promo")).id,
        parameters={"symbol_code": "005930"},
    )
    days = [
        (datetime(2026, 6, 1, 10, tzinfo=timezone.utc), Decimal("100")),
        (datetime(2026, 6, 2, 10, tzinfo=timezone.utc), Decimal("-40")),
        (datetime(2026, 6, 5, 10, tzinfo=timezone.utc), Decimal("60")),
    ]
    for ts, pnl in days:
        session.add(
            Trade(account_id=account.id, strategy_version_id=version.id, symbol_code="005930",
                  side=TradeSide.BUY, quantity=1, pnl_amount=pnl,
                  order_status=OrderStatus.FILLED, created_at=ts)
        )
    await session.commit()
    return version.id


async def test_promotion_pass(db_session: AsyncSession) -> None:
    version_id = await _seed_version_with_trades(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            criteria_id = (
                await client.post(
                    "/api/v1/promotion-criteria",
                    json={
                        "name": "lenient",
                        "min_trade_count": 2,
                        "min_days": 2,
                        "min_expectancy": "0",
                        "max_drawdown": "1000",
                    },
                )
            ).json()["id"]

            ev = await client.post(
                f"/api/v1/strategy-versions/{version_id}/promotion-evaluation",
                params={"criteria_id": criteria_id},
            )
            assert ev.status_code == 200
            body = ev.json()
            assert body["passed"] is True
            assert body["trades_count"] == 3
            assert body["days"] == 4
            assert Decimal(body["expectancy"]) == Decimal("40")
            assert Decimal(body["max_drawdown"]) == Decimal("40")
            assert all(c["passed"] for c in body["checks"])
    finally:
        app.dependency_overrides.clear()


async def test_promotion_fail_on_trade_count(db_session: AsyncSession) -> None:
    version_id = await _seed_version_with_trades(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            criteria_id = (
                await client.post(
                    "/api/v1/promotion-criteria",
                    json={"name": "strict", "min_trade_count": 100, "min_days": 0},
                )
            ).json()["id"]

            ev = await client.post(
                f"/api/v1/strategy-versions/{version_id}/promotion-evaluation",
                params={"criteria_id": criteria_id, "persist": "true"},
            )
            body = ev.json()
            assert body["passed"] is False
            failed = next(c for c in body["checks"] if c["name"] == "min_trade_count")
            assert failed["passed"] is False
            assert failed["actual"] == "3"
            assert failed["threshold"] == "100"

            # persist=true 였으므로 평가 이력이 저장됨
            from app.domain.models.promotion import PromotionEvaluation
            from sqlalchemy import select

            rows = (await db_session.execute(select(PromotionEvaluation))).scalars().all()
            assert len(rows) == 1
            assert rows[0].passed is False
    finally:
        app.dependency_overrides.clear()


async def test_evaluate_unknown_version_and_criteria_404(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            criteria_id = (
                await client.post("/api/v1/promotion-criteria", json={"name": "c"})
            ).json()["id"]

            no_version = await client.post(
                "/api/v1/strategy-versions/999999/promotion-evaluation",
                params={"criteria_id": criteria_id},
            )
            assert no_version.status_code == 404

            version_id = await _seed_version_with_trades(db_session)
            no_criteria = await client.post(
                f"/api/v1/strategy-versions/{version_id}/promotion-evaluation",
                params={"criteria_id": 999999},
            )
            assert no_criteria.status_code == 404
    finally:
        app.dependency_overrides.clear()
