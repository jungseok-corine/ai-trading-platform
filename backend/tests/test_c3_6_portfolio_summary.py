"""C-3.6 보유 포지션·노출 집계 테스트."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType
from app.domain.models.position import Position
from app.services.portfolio_summary_service import PortfolioSummaryService


async def _account(session: AsyncSession) -> Account:
    acc = Account(account_type=AccountType.PAPER, broker_account_no="50192525-01", alias="t")
    session.add(acc)
    await session.flush()
    return acc


async def test_summary_aggregates_and_exposure(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    db_session.add_all([
        # 시총 750,000 (10 * 75000), cost 700,000, 미실현 +50,000
        Position(account_id=acc.id, symbol_code="005930", symbol_name="삼성전자",
                 quantity=10, avg_entry_price=Decimal("70000"), last_price=Decimal("75000"),
                 unrealized_pnl=Decimal("50000"), realized_pnl=Decimal("10000")),
        # 시총 250,000 (5 * 50000), cost 300,000, 미실현 -50,000
        Position(account_id=acc.id, symbol_code="000660", symbol_name="SK하이닉스",
                 quantity=5, avg_entry_price=Decimal("60000"), last_price=Decimal("50000"),
                 unrealized_pnl=Decimal("-50000"), realized_pnl=Decimal("0")),
        # 청산된 포지션(수량 0) → 제외
        Position(account_id=acc.id, symbol_code="035720", quantity=0,
                 avg_entry_price=Decimal("0"), unrealized_pnl=Decimal("0")),
    ])
    await db_session.flush()

    out = await PortfolioSummaryService(db_session).summary()
    assert out["open_positions"] == 2
    assert out["total_market_value"] == 1_000_000.0
    assert out["total_cost_basis"] == 1_000_000.0
    assert out["total_unrealized_pnl"] == 0.0
    assert out["total_realized_pnl"] == 10000.0
    # 시총 큰 종목이 먼저(삼성전자 750k)
    top = out["positions"][0]
    assert top["symbol_code"] == "005930"
    assert top["exposure_pct"] == 75.0
    assert top["unrealized_pct"] == round(50000 / 700000 * 100, 2)


async def test_summary_handles_missing_price(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    db_session.add(Position(
        account_id=acc.id, symbol_code="005930", quantity=10,
        avg_entry_price=Decimal("70000"), last_price=None, unrealized_pnl=Decimal("0"),
    ))
    await db_session.flush()
    out = await PortfolioSummaryService(db_session).summary()
    p = out["positions"][0]
    # last_price 없으면 avg로 평가
    assert p["has_price"] is False
    assert p["market_value"] == 700000.0


async def test_summary_filters_by_account(db_session: AsyncSession) -> None:
    a1 = await _account(db_session)
    a2 = Account(account_type=AccountType.PAPER, broker_account_no="50192525-02")
    db_session.add(a2)
    await db_session.flush()
    db_session.add_all([
        Position(account_id=a1.id, symbol_code="005930", quantity=1,
                 avg_entry_price=Decimal("100"), last_price=Decimal("100")),
        Position(account_id=a2.id, symbol_code="000660", quantity=1,
                 avg_entry_price=Decimal("200"), last_price=Decimal("200")),
    ])
    await db_session.flush()
    out = await PortfolioSummaryService(db_session).summary(account_id=a2.id)
    assert out["open_positions"] == 1
    assert out["positions"][0]["symbol_code"] == "000660"
