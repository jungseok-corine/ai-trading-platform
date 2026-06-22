"""C-5.16: 혼합 통화 리스크 집계 + 일시적 오류 분류(로그 노이즈 억제)."""
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, TradeSide
from app.domain.models.trade import Trade
from app.trading.broker.error_classifier import (
    KIS_ERROR_RATE_LIMIT,
    KIS_ERROR_TOKEN,
    is_transient_error,
)
from app.trading.risk.context import RiskContextBuilder

KST = ZoneInfo("Asia/Seoul")


class _FakeBroker:
    async def get_account_balance(self):
        from app.trading.broker.schemas import AccountBalance, AccountSummary

        return AccountBalance(
            holdings=[],
            summary=AccountSummary(
                total_deposit=Decimal("0"), total_purchase_amount=Decimal("0"),
                total_evaluation_amount=Decimal("0"), total_profit_loss_amount=Decimal("0"),
            ),
        )


# --------------------------------------------------------------------------- #
# ① 혼합 통화 당일손익 (US PnL을 KRW로 환산해 합산)
# --------------------------------------------------------------------------- #


async def test_today_realized_pnl_converts_us_to_krw(db_session: AsyncSession) -> None:
    acc = Account(account_type=AccountType.PAPER, broker_account_no="50000000-01")
    db_session.add(acc)
    await db_session.flush()
    now = datetime.now(KST)
    db_session.add_all([
        # KR: -10,000원 손실
        Trade(account_id=acc.id, symbol_code="005930", market="KR", side=TradeSide.SELL,
              quantity=1, pnl_amount=Decimal("-10000"), order_status=OrderStatus.FILLED,
              exit_time=now - timedelta(minutes=5)),
        # US: -$10 손실 → 환산 -13,500원 (usd_krw_rate=1350)
        Trade(account_id=acc.id, symbol_code="AAPL", market="US", side=TradeSide.SELL,
              quantity=1, pnl_amount=Decimal("-10"), order_status=OrderStatus.FILLED,
              exit_time=now - timedelta(minutes=5)),
    ])
    await db_session.commit()

    ctx = await RiskContextBuilder(db_session, _FakeBroker()).build(acc.id)

    # -10,000(KR) + -10×1350(US) = -23,500원
    assert ctx.today_realized_pnl == Decimal("-23500")


# --------------------------------------------------------------------------- #
# ② 일시적 오류 분류
# --------------------------------------------------------------------------- #


def test_transient_error_classification() -> None:
    assert is_transient_error(KIS_ERROR_RATE_LIMIT) is True   # 레이트리밋 → 일시적
    assert is_transient_error("market_closed") is True        # 장외 → 일시적
    assert is_transient_error("connection_timeout") is False  # 네트워크는 실제 문제일 수 있어 실패 유지
    assert is_transient_error(KIS_ERROR_TOKEN) is False       # 토큰 오류 → 실질적
    assert is_transient_error("insufficient_balance") is False
    assert is_transient_error("unknown") is False
    assert is_transient_error(None) is False
