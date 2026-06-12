from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker_client
from app.db.session import get_db
from app.domain.models.account import Account
from app.domain.models.enums import AccountType, TradeSide
from app.main import app
from app.services.position_service import PositionService
from app.trading.broker.base import BrokerClient
from app.trading.broker.schemas import (
    AccountBalance,
    AccountSummary,
    MinuteCandle,
    OrderExecution,
    OrderRequest,
    OrderResult,
    PriceQuote,
)


class FakeBrokerClient(BrokerClient):
    async def get_current_price(self, symbol_code: str) -> PriceQuote:
        return PriceQuote(
            symbol_code=symbol_code,
            current_price=Decimal("80000"),
            change=Decimal("0"),
            change_rate=Decimal("0"),
            open_price=Decimal("80000"),
            high_price=Decimal("80000"),
            low_price=Decimal("80000"),
            volume=0,
        )

    async def get_minute_candles(
        self, symbol_code: str, target_time: str | None = None, include_past_data: bool = True
    ) -> list[MinuteCandle]:
        raise NotImplementedError

    async def get_account_balance(self) -> AccountBalance:
        return AccountBalance(
            holdings=[],
            summary=AccountSummary(
                total_deposit=Decimal("0"),
                total_purchase_amount=Decimal("0"),
                total_evaluation_amount=Decimal("0"),
                total_profit_loss_amount=Decimal("0"),
            ),
        )

    async def place_order(self, order: OrderRequest) -> OrderResult:
        raise NotImplementedError

    async def get_daily_executions(self, target_date: str | None = None) -> list[OrderExecution]:
        return []


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _create_account(session: AsyncSession) -> Account:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000-01")
    session.add(account)
    await session.flush()
    return account


async def test_positions_api_flow(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    position = await PositionService(db_session).apply_fill(
        account_id=account.id,
        symbol_code="005930",
        symbol_name="삼성전자",
        side=TradeSide.BUY,
        quantity=10,
        price=Decimal("70000"),
    )

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    app.dependency_overrides[get_broker_client] = lambda: FakeBrokerClient()

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            list_resp = await client.get("/api/v1/positions", params={"account_id": account.id})
            assert list_resp.status_code == 200
            positions = list_resp.json()
            assert len(positions) == 1
            assert positions[0]["symbol_code"] == "005930"

            detail_resp = await client.get(f"/api/v1/positions/{account.id}/005930")
            assert detail_resp.status_code == 200
            detail = detail_resp.json()
            assert detail["id"] == position.id
            assert Decimal(detail["avg_entry_price"]) == Decimal("70000")
            assert Decimal(detail["quantity"]) == 10

            missing_resp = await client.get(f"/api/v1/positions/{account.id}/000000")
            assert missing_resp.status_code == 404

            events_resp = await client.get(f"/api/v1/positions/{position.id}/events")
            assert events_resp.status_code == 200
            events = events_resp.json()
            assert len(events) == 1
            assert events[0]["event_type"] == "buy_fill"
            assert events[0]["quantity_delta"] == 10

            refresh_resp = await client.post(f"/api/v1/positions/{position.id}/refresh-price")
            assert refresh_resp.status_code == 200
            refreshed = refresh_resp.json()
            assert Decimal(refreshed["last_price"]) == Decimal("80000")
            assert Decimal(refreshed["unrealized_pnl"]) == (Decimal("80000") - Decimal("70000")) * 10

            summary_resp = await client.get("/api/v1/portfolio/summary", params={"account_id": account.id})
            assert summary_resp.status_code == 200
            summary = summary_resp.json()
            assert summary["account_id"] == account.id
            assert summary["position_count"] == 1
            assert Decimal(summary["total_quantity"]) == 10
            assert Decimal(summary["total_unrealized_pnl"]) == (Decimal("80000") - Decimal("70000")) * 10

            refresh_all_resp = await client.post(
                "/api/v1/positions/refresh-prices", params={"account_id": account.id}
            )
            assert refresh_all_resp.status_code == 200
            refresh_all = refresh_all_resp.json()
            assert refresh_all["updated"] == 1
            assert Decimal(refresh_all["positions"][0]["last_price"]) == Decimal("80000")
    finally:
        app.dependency_overrides.clear()
