"""PAPER-RESUME-4D-GUARD — 미보유 종목 SELL auto-trade 스킵 테스트.

_attempt_auto_trade에서 SELL 신호인데 브로커 보유수량 0이면 execute_signal(broker) 호출 전에 스킵.
보유수량은 SL/TP 판정과 동일하게 trade_service.get_holdings(=브로커 잔고)로 확인. BUY / 보유 SELL은 유지.
"""
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import (
    AccountType,
    StrategyVersionStatus,
    TradeAttemptStatus,
    TradeSide,
)
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.trade import Trade
from app.services.strategy_runner_service import StrategyRunResult, StrategyRunnerService
from app.services.trade_service import OrderPlacementResult
from app.trading.broker.schemas import AccountHolding

KST = ZoneInfo("Asia/Seoul")


async def _account(session) -> Account:
    acc = Account(account_type=AccountType.PAPER, broker_account_no="00000000-01")
    session.add(acc)
    await session.flush()
    return acc


async def _version(session) -> StrategyVersion:
    s = Strategy(name="g")
    session.add(s)
    await session.flush()
    v = StrategyVersion(strategy_id=s.id, version_no=1,
                        parameters={"strategy_type": "moving_average_cross"},
                        status=StrategyVersionStatus.TESTING)
    session.add(v)
    await session.flush()
    return v


async def _signal(session, version_id, symbol, side) -> SignalLog:
    log = SignalLog(
        symbol_code=symbol, market="KR", timeframe="1m", strategy_version_id=version_id,
        signal_type=side, generated_at=datetime.now(KST), price=Decimal("317750"), quantity=1,
        trade_attempt_status=TradeAttemptStatus.NOT_ATTEMPTED)
    session.add(log)
    await session.flush()
    return log


def _holding(symbol, qty) -> AccountHolding:
    return AccountHolding(
        symbol_code=symbol, symbol_name=symbol, quantity=qty, avg_purchase_price=Decimal("300000"),
        current_price=Decimal("317750"), evaluation_amount=Decimal("317750") * qty,
        profit_loss_amount=Decimal("0"), profit_loss_rate=Decimal("0"))


def _runner(session, trade_service):
    return StrategyRunnerService(session, MagicMock(), trade_service)


def _params(account_id):
    return {"strategy_type": "moving_average_cross", "market": "KR", "account_id": account_id, "quantity": 1}


def _mock_trade_service(holdings=None):
    ts = MagicMock()
    ts.get_holdings = AsyncMock(return_value=holdings or {})
    # execute_signal 호출 여부만 검증(실제 trades row 없이 FK 미접촉하도록 approved=False).
    ts.execute_signal = AsyncMock(return_value=OrderPlacementResult(
        approved=False, trade=None, rule_name="mock", reason="mock (execute_signal reached)"))
    return ts


def _result(v, symbol, log):
    return StrategyRunResult(strategy_version_id=v.id, symbol_code=symbol, signal_created=True,
                             signal_id=log.id, auto_trade_enabled=True, trade_attempted=False)


# --- Test 1: SELL without holding is skipped before broker ------------------
async def test_sell_without_holding_skipped(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    v = await _version(db_session)
    log = await _signal(db_session, v.id, "005930", TradeSide.SELL)
    trades_before = (await db_session.execute(select(func.count()).select_from(Trade))).scalar_one()
    ts = _mock_trade_service(holdings={})  # 미보유
    result = _result(v, "005930", log)

    await _runner(db_session, ts)._attempt_auto_trade(v, _params(acc.id), log, result)

    ts.execute_signal.assert_not_called()
    assert result.trade_attempted is False
    assert "sell_without_holding" in (result.rejection_reason or "")
    refreshed = await db_session.get(SignalLog, log.id)
    assert refreshed.trade_attempt_status == TradeAttemptStatus.REJECTED
    assert (await db_session.execute(select(func.count()).select_from(Trade))).scalar_one() == trades_before


# --- Test 2: SELL with holding is allowed -----------------------------------
async def test_sell_with_holding_allowed(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    v = await _version(db_session)
    log = await _signal(db_session, v.id, "005930", TradeSide.SELL)
    ts = _mock_trade_service(holdings={"005930": _holding("005930", 3)})  # 보유 3주
    result = _result(v, "005930", log)

    await _runner(db_session, ts)._attempt_auto_trade(v, _params(acc.id), log, result)

    ts.execute_signal.assert_called_once()  # 정상 청산 경로
    assert result.trade_attempted is True


# --- Test 3: BUY without holding is not blocked -----------------------------
async def test_buy_without_holding_not_blocked(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    v = await _version(db_session)
    log = await _signal(db_session, v.id, "005930", TradeSide.BUY)
    ts = _mock_trade_service(holdings={})
    result = _result(v, "005930", log)

    await _runner(db_session, ts)._attempt_auto_trade(v, _params(acc.id), log, result)

    ts.execute_signal.assert_called_once()  # BUY는 guard 미적용
    ts.get_holdings.assert_not_called()     # BUY는 잔고 조회도 안 함
    assert result.trade_attempted is True


# --- Test 4: v329-like 005930 SELL with 0 holding is skipped ----------------
async def test_v329_like_sell_skipped(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    v = await _version(db_session)
    log = await _signal(db_session, v.id, "005930", TradeSide.SELL)
    ts = _mock_trade_service(holdings={"000660": _holding("000660", 5)})  # 005930은 미보유
    result = _result(v, "005930", log)

    await _runner(db_session, ts)._attempt_auto_trade(v, _params(acc.id), log, result)

    ts.execute_signal.assert_not_called()
    assert "no position to sell" in (result.rejection_reason or "")


# --- Test 5: guard triggers only for SELL -----------------------------------
@pytest.mark.parametrize("side,expect_called", [(TradeSide.SELL, False), (TradeSide.BUY, True)])
async def test_guard_only_affects_sell(db_session: AsyncSession, side, expect_called) -> None:
    acc = await _account(db_session)
    v = await _version(db_session)
    log = await _signal(db_session, v.id, "000660", side)
    ts = _mock_trade_service(holdings={})  # 미보유
    result = _result(v, "000660", log)

    await _runner(db_session, ts)._attempt_auto_trade(v, _params(acc.id), log, result)

    assert ts.execute_signal.called is expect_called
