"""C-3.23 포지션 집중 위험 다이제스트 경보 테스트."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType
from app.domain.models.position import Position
from app.services.operations_digest_service import OperationsDigestService


async def test_concentrated_position_alerts(db_session: AsyncSession) -> None:
    acc = Account(account_type=AccountType.PAPER, broker_account_no="50192525-01")
    db_session.add(acc)
    await db_session.flush()
    # 한 종목이 100% 노출 → 집중 경보
    db_session.add(Position(
        account_id=acc.id, symbol_code="005930", quantity=10,
        avg_entry_price=Decimal("70000"), last_price=Decimal("70000"),
        unrealized_pnl=Decimal("0"),
    ))
    await db_session.flush()

    digest = await OperationsDigestService(db_session).build()
    assert any("포지션 집중" in a["text"] and "005930" in a["text"] for a in digest["alerts"])


async def test_diversified_no_alert(db_session: AsyncSession) -> None:
    acc = Account(account_type=AccountType.PAPER, broker_account_no="50192525-01")
    db_session.add(acc)
    await db_session.flush()
    # 두 종목 균등(각 50% < 임계 아님? 50<40? no 50>=40 → 둘 다 경보).
    # 임계 미만이 되도록 3종목 균등(각 ~33%)
    for sym in ("005930", "000660", "035720"):
        db_session.add(Position(
            account_id=acc.id, symbol_code=sym, quantity=1,
            avg_entry_price=Decimal("100"), last_price=Decimal("100"),
            unrealized_pnl=Decimal("0"),
        ))
    await db_session.flush()

    digest = await OperationsDigestService(db_session).build()
    assert not any("포지션 집중" in a["text"] for a in digest["alerts"])
