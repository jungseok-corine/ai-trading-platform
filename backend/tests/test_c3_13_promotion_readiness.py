"""C-3.13 승격 준비 현황 보드 테스트."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, StrategyVersionStatus, TradeSide
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.trade import Trade
from app.services.promotion_readiness_service import PromotionReadinessService
from app.services.promotion_service import PromotionService


async def test_board_without_criteria(db_session: AsyncSession) -> None:
    out = await PromotionReadinessService(db_session).board()
    assert out["criteria"] is None
    assert out["rows"] == []


async def test_board_evaluates_active_versions(db_session: AsyncSession) -> None:
    acc = Account(account_type=AccountType.PAPER, broker_account_no="50192525-01")
    strat = Strategy(name="ReadyStrat", description="t")
    db_session.add_all([acc, strat])
    await db_session.flush()
    sv = StrategyVersion(strategy_id=strat.id, version_no=1,
                         parameters={"strategy_type": "moving_average_cross"},
                         status=StrategyVersionStatus.TESTING)
    db_session.add(sv)
    await db_session.flush()
    # 승리 거래 3건
    for _ in range(3):
        db_session.add(Trade(
            account_id=acc.id, strategy_version_id=sv.id, symbol_code="005930",
            side=TradeSide.BUY, quantity=1, order_status=OrderStatus.FILLED,
            pnl_amount=Decimal("1000"),
        ))
    await db_session.flush()

    # 기준: 최소 2건, 0일, 기댓값 0 이상 → 통과 가능(단 min_days 충족은 거래 간격에 의존)
    await PromotionService(db_session).create_criteria(
        name="loose", min_trade_count=2, min_days=0, min_expectancy=Decimal("0"),
    )

    out = await PromotionReadinessService(db_session).board()
    assert out["criteria"] is not None
    assert len(out["rows"]) == 1
    row = out["rows"][0]
    assert row["label"] == "ReadyStrat v1"
    assert row["trades_count"] == 3
    assert row["checks_total"] >= 3
    assert "실거래 활성화는 사람만" in out["note"]
