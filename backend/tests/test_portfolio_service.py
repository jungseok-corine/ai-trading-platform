from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, TradeSide
from app.services.portfolio_service import PortfolioService
from app.services.position_service import PositionService


async def _create_account(session: AsyncSession) -> Account:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000-01")
    session.add(account)
    await session.flush()
    return account


async def test_portfolio_summary_for_account_with_no_positions(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)

    summary = await PortfolioService(db_session).get_summary(account.id)

    assert summary.account_id == account.id
    assert summary.position_count == 0
    assert summary.total_quantity == 0
    assert summary.total_cost_amount == Decimal("0")
    assert summary.total_eval_amount == Decimal("0")
    assert summary.total_unrealized_pnl == Decimal("0")
    assert summary.total_unrealized_pnl_pct == Decimal("0")
    assert summary.total_realized_pnl == Decimal("0")
    assert summary.total_pnl == Decimal("0")


async def test_portfolio_summary_aggregates_open_positions(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    position_service = PositionService(db_session)

    # 005930: 10주 매수 @70000, 현재가 80000으로 평가
    position = await position_service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=10,
        price=Decimal("70000"),
    )
    await position_service.update_last_price(account.id, "005930", Decimal("80000"))

    # 000660: 5주 매수 @100000, 시세 미갱신 (last_price=avg_entry_price로 평가)
    await position_service.apply_fill(
        account_id=account.id,
        symbol_code="000660",
        side=TradeSide.BUY,
        quantity=5,
        price=Decimal("100000"),
    )

    summary = await PortfolioService(db_session).get_summary(account.id)

    assert summary.position_count == 2
    assert summary.total_quantity == 15
    # cost = 70000*10 + 100000*5 = 1,200,000
    assert summary.total_cost_amount == Decimal("1200000")
    # eval = 80000*10 + 100000*5 = 1,300,000 (000660은 last_price 미설정 -> avg_entry_price로 평가)
    assert summary.total_eval_amount == Decimal("1300000")
    # unrealized = (80000-70000)*10 + 0 = 100,000
    assert summary.total_unrealized_pnl == Decimal("100000")
    # pct = 100000 / 1200000 * 100
    assert summary.total_unrealized_pnl_pct.quantize(Decimal("0.0001")) == (
        Decimal("100000") / Decimal("1200000") * 100
    ).quantize(Decimal("0.0001"))
    assert summary.total_realized_pnl == Decimal("0")
    assert summary.total_pnl == Decimal("100000")
    assert position.id is not None


async def test_portfolio_summary_excludes_closed_positions_from_eval_amount(db_session: AsyncSession) -> None:
    account = await _create_account(db_session)
    position_service = PositionService(db_session)

    await position_service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        side=TradeSide.BUY,
        quantity=10,
        price=Decimal("70000"),
    )
    await position_service.apply_fill(
        account_id=account.id,
        symbol_code="005930",
        side=TradeSide.SELL,
        quantity=10,
        price=Decimal("80000"),
    )

    summary = await PortfolioService(db_session).get_summary(account.id)

    # quantity == 0 인 포지션은 보유종목 수/매입금액/평가금액 계산에서 제외된다
    assert summary.position_count == 0
    assert summary.total_quantity == 0
    assert summary.total_cost_amount == Decimal("0")
    assert summary.total_eval_amount == Decimal("0")
    assert summary.total_unrealized_pnl == Decimal("0")
    # 실현손익은 종목이 청산되어도 유지된다
    assert summary.total_realized_pnl == Decimal("100000")
    assert summary.total_pnl == Decimal("100000")
