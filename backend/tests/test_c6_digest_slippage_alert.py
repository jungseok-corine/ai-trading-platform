"""C-6.10: 다이제스트 슬리피지 경보 — 표본 충분 + 평균 슬리피지 임계 초과 시에만."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, TradeSide
from app.domain.models.signal_log import SignalLog
from app.domain.models.trade import Trade
from app.services.operations_digest_service import OperationsDigestService


async def _pairs(session: AsyncSession, n: int, signal_price: int, fill_price: int) -> None:
    acc = Account(account_type=AccountType.PAPER, broker_account_no="00000000-01")
    session.add(acc)
    await session.flush()
    now = datetime.now(timezone.utc)
    for i in range(n):
        trade = Trade(
            account_id=acc.id, symbol_code=f"SL{i:04d}", side=TradeSide.BUY,
            quantity=1, entry_price=Decimal(fill_price), entry_time=now,
            order_status=OrderStatus.FILLED,
        )
        session.add(trade)
        await session.flush()
        session.add(
            SignalLog(
                symbol_code=f"SL{i:04d}", signal_type=TradeSide.BUY,
                generated_at=now, price=Decimal(signal_price), trade_id=trade.id,
            )
        )
    await session.commit()


def _slippage_alerts(digest: dict) -> list[dict]:
    return [a for a in digest["alerts"] if "체결 품질" in a["text"]]


@pytest.mark.asyncio
async def test_alert_when_slippage_high_with_enough_samples(db_session: AsyncSession):
    # 10건, 슬리피지 +1% → 경보
    await _pairs(db_session, 10, signal_price=10000, fill_price=10100)
    digest = await OperationsDigestService(db_session).build(days=7)
    alerts = _slippage_alerts(digest)
    assert len(alerts) == 1
    assert alerts[0]["level"] == "attention"


@pytest.mark.asyncio
async def test_no_alert_with_small_sample(db_session: AsyncSession):
    # 3건뿐 — 소표본 소음 방지
    await _pairs(db_session, 3, signal_price=10000, fill_price=10300)
    digest = await OperationsDigestService(db_session).build(days=7)
    assert _slippage_alerts(digest) == []


@pytest.mark.asyncio
async def test_no_alert_when_slippage_low(db_session: AsyncSession):
    # 10건이지만 슬리피지 +0.1% — 임계 미만
    await _pairs(db_session, 10, signal_price=10000, fill_price=10010)
    digest = await OperationsDigestService(db_session).build(days=7)
    assert _slippage_alerts(digest) == []
