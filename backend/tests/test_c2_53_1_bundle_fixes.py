"""C-2.53.1 분석 번들 보정: 매크로 룩어헤드 / 미청산 라벨 / 장중 필터."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType
from app.domain.models.market_data import MarketData
from app.domain.models.news_context import UsMarketSnapshot
from app.services.macro_regime_service import MacroRegimeService
from app.services.strategy_service import StrategyService
from app.services.trade_tape_service import TradeTapeService
from app.trading.analysis.trade_tape import Candle, TradeEvent, build_trade_tape

KST = ZoneInfo("Asia/Seoul")


# --- 1. 매크로 룩어헤드 방지 ------------------------------------------------
async def test_regime_as_of_excludes_same_day_and_future(db_session: AsyncSession) -> None:
    # 06-16: risk_on(저VIX+상승) / 06-18: risk_off(고VIX). trading_day=06-18 분석은
    # 06-18 미국장(미래)을 보면 안 되고, 직전 세션(06-16) 기준이어야 한다.
    db_session.add(UsMarketSnapshot(session_date=date(2026, 6, 16), vix=Decimal("12.0"),
                                    nasdaq_change_pct=Decimal("1.5"), sp500_change_pct=Decimal("1.2")))
    db_session.add(UsMarketSnapshot(session_date=date(2026, 6, 18), vix=Decimal("33.0"),
                                    nasdaq_change_pct=Decimal("-2.0")))
    await db_session.commit()

    svc = MacroRegimeService(db_session)
    as_of = await svc.regime_as_of(date(2026, 6, 18))
    latest = await svc.latest_regime()

    assert as_of["regime"] == "risk_on"  # 06-16 (룩어헤드 차단)
    assert as_of["session_date"] == "2026-06-16"
    assert latest["regime"] == "risk_off"  # 최신은 06-18 (대조)


async def test_regime_as_of_unknown_when_no_prior(db_session: AsyncSession) -> None:
    db_session.add(UsMarketSnapshot(session_date=date(2026, 6, 18), vix=Decimal("20.0")))
    await db_session.commit()
    # 직전(< 06-18) 데이터가 없으면 unknown
    r = await MacroRegimeService(db_session).regime_as_of(date(2026, 6, 18))
    assert r["regime"] == "unknown"


# --- 2. 미청산 주문 라벨링 --------------------------------------------------
def test_open_vs_closed_trade_labeling() -> None:
    T0 = datetime(2026, 6, 17, 9, 0, tzinfo=KST)
    candles = [Candle(ts=T0 + timedelta(minutes=i), o=100, h=106, lo=98, c=100 + i, v=10)
               for i in range(10)]
    closed = TradeEvent(side="buy", quantity=1, entry_time=T0,
                        exit_time=T0 + timedelta(minutes=3), entry_price=100.0, pnl_pct=1.0)
    open_t = TradeEvent(side="buy", quantity=1, entry_time=T0, entry_price=100.0)  # exit 없음

    tape = build_trade_tape(candles, [closed, open_t], window=2, coarse=5)
    by_status = {t["status"]: t for t in tape["trades"]}
    assert by_status["closed"]["features"]["excursion_basis"] == "to_exit"
    assert by_status["open"]["features"]["excursion_basis"] == "to_session_close"
    assert by_status["open"]["features"]["realized_return_pct"] is None


# --- 3. 장중(09:00~15:30 KST) 필터 -----------------------------------------
async def test_session_filter_drops_postclose(db_session: AsyncSession) -> None:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000")
    db_session.add(account)
    await db_session.commit()
    svc = StrategyService(db_session)
    strategy = await svc.create_strategy("sess")
    version = await svc.create_version(strategy.id, parameters={"symbol_code": "005930"})

    base = datetime(2026, 6, 17, 0, 0, tzinfo=KST)
    # 장중: 09:00, 15:30  / 장외: 08:30, 16:00
    times = {"08:30": base.replace(hour=8, minute=30), "09:00": base.replace(hour=9),
             "15:30": base.replace(hour=15, minute=30), "16:00": base.replace(hour=16)}
    for ts in times.values():
        db_session.add(MarketData(symbol_code="005930", timeframe="1m", ts=ts,
                                  open=Decimal("100"), high=Decimal("101"), low=Decimal("99"),
                                  close=Decimal("100"), volume=1000))
    await db_session.commit()

    tape = await TradeTapeService(db_session).build_for_version(version.id, date(2026, 6, 17))
    # 09:00, 15:30 두 개만 (08:30, 16:00 제외)
    assert tape["day_summary"]["candle_count"] == 2

    # 필터 끄면 4개 전부
    tape_all = await TradeTapeService(db_session).build_for_version(
        version.id, date(2026, 6, 17), regular_session_only=False
    )
    assert tape_all["day_summary"]["candle_count"] == 4
