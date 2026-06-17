"""MarketDataService / MarketDataRepository DB 통합 테스트."""
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.market_data import MarketData
from app.domain.repositories.market_data import MarketDataRepository
from app.services.market_data_service import MarketDataService, _candle_ts
from app.trading.broker.base import BrokerClient
from app.trading.broker.schemas import (
    AccountBalance,
    AccountHolding,
    AccountSummary,
    MinuteCandle,
    OrderExecution,
    OrderRequest,
    OrderResult,
    PriceQuote,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _candle(business_date: str, trade_time: str, close: int = 100) -> MinuteCandle:
    price = Decimal(close)
    return MinuteCandle(
        business_date=business_date,
        trade_time=trade_time,
        open_price=price,
        high_price=price,
        low_price=price,
        close_price=price,
        volume=1000,
    )


def _candles(n: int, symbol_close: int = 100) -> list[MinuteCandle]:
    """n개의 분봉을 2026-06-10 09:00~09:(n-1)분으로 생성한다."""
    result = []
    for i in range(n):
        mm = i % 60
        hh = 9 + i // 60
        result.append(_candle("20260610", f"{hh:02d}{mm:02d}00", close=symbol_close))
    return result


class FakeBroker(BrokerClient):
    def __init__(self, candles: list[MinuteCandle] | None = None) -> None:
        self._candles = candles or []

    async def get_current_price(self, symbol_code: str) -> PriceQuote:
        raise NotImplementedError

    async def get_minute_candles(
        self, symbol_code: str, target_time: str | None = None, include_past_data: bool = True
    ) -> list[MinuteCandle]:
        return self._candles

    async def get_account_balance(self) -> AccountBalance:
        raise NotImplementedError

    async def get_account_positions(self) -> list[AccountHolding]:
        return []

    async def place_order(self, order: OrderRequest) -> OrderResult:
        raise NotImplementedError

    async def get_daily_executions(self, start_date: str | None = None, end_date: str | None = None) -> list[OrderExecution]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# _candle_ts 변환 단위 테스트
# ---------------------------------------------------------------------------


def test_candle_ts_converts_to_kst() -> None:
    from zoneinfo import ZoneInfo
    ts = _candle_ts("20260610", "090000")
    assert ts.year == 2026
    assert ts.month == 6
    assert ts.day == 10
    assert ts.hour == 9
    assert ts.minute == 0
    assert ts.tzinfo == ZoneInfo("Asia/Seoul")


# ---------------------------------------------------------------------------
# 1. 캔들 저장 기본
# ---------------------------------------------------------------------------


async def test_save_candles_persists_to_db(db_session: AsyncSession) -> None:
    svc = MarketDataService(FakeBroker(), db_session)
    candles = _candles(5)

    saved = await svc.save_candles("005930", "1m", candles)
    await db_session.commit()  # save_candles는 flush만 하므로 테스트에서 직접 commit

    assert saved == 5
    rows = (await db_session.execute(select(MarketData))).scalars().all()
    assert len(rows) == 5
    assert all(r.symbol_code == "005930" for r in rows)
    assert all(r.timeframe == "1m" for r in rows)


# ---------------------------------------------------------------------------
# 2. 중복 저장 방지
# ---------------------------------------------------------------------------


async def test_save_candles_no_duplicates_on_second_call(db_session: AsyncSession) -> None:
    svc = MarketDataService(FakeBroker(), db_session)
    candles = _candles(3)

    await svc.save_candles("005930", "1m", candles)
    await svc.save_candles("005930", "1m", candles)  # 동일 데이터 재저장
    await db_session.commit()

    rows = (await db_session.execute(select(MarketData))).scalars().all()
    assert len(rows) == 3  # 중복 row 없음


async def test_upsert_updates_ohlcv_on_conflict(db_session: AsyncSession) -> None:
    svc = MarketDataService(FakeBroker(), db_session)
    original = [_candle("20260610", "090000", close=100)]
    await svc.save_candles("005930", "1m", original)
    await db_session.commit()

    updated = [_candle("20260610", "090000", close=200)]
    await svc.save_candles("005930", "1m", updated)
    await db_session.commit()

    rows = (await db_session.execute(select(MarketData))).scalars().all()
    assert len(rows) == 1
    assert rows[0].close == Decimal("200")


# ---------------------------------------------------------------------------
# 3. 다른 symbol_code는 별도 저장
# ---------------------------------------------------------------------------


async def test_different_symbols_stored_separately(db_session: AsyncSession) -> None:
    svc = MarketDataService(FakeBroker(), db_session)
    candles = _candles(3)

    await svc.save_candles("005930", "1m", candles)
    await svc.save_candles("035420", "1m", candles)
    await db_session.commit()

    rows = (await db_session.execute(select(MarketData))).scalars().all()
    assert len(rows) == 6
    codes = {r.symbol_code for r in rows}
    assert codes == {"005930", "035420"}


# ---------------------------------------------------------------------------
# 4. 같은 symbol이라도 timeframe이 다르면 별도 저장
# ---------------------------------------------------------------------------


async def test_different_timeframes_stored_separately(db_session: AsyncSession) -> None:
    svc = MarketDataService(FakeBroker(), db_session)
    candles = _candles(3)

    await svc.save_candles("005930", "1m", candles)
    await svc.save_candles("005930", "5m", candles)
    await db_session.commit()

    rows = (await db_session.execute(select(MarketData))).scalars().all()
    assert len(rows) == 6
    timeframes = {r.timeframe for r in rows}
    assert timeframes == {"1m", "5m"}


# ---------------------------------------------------------------------------
# 5. get_recent_candles가 session 주입 시 DB에 저장
# ---------------------------------------------------------------------------


async def test_get_recent_candles_saves_to_db_when_session_given(db_session: AsyncSession) -> None:
    candles = _candles(10)
    svc = MarketDataService(FakeBroker(candles), db_session)

    # get_recent_candles는 flush만 하므로 commit은 여기서
    result = await svc.get_recent_candles("005930", timeframe="1m")
    await db_session.commit()

    assert len(result) == 10
    rows = (await db_session.execute(select(MarketData))).scalars().all()
    assert len(rows) == 10


async def test_get_recent_candles_does_not_save_without_session() -> None:
    candles = _candles(5)
    svc = MarketDataService(FakeBroker(candles))  # session 없음

    result = await svc.get_recent_candles("005930")
    assert len(result) == 5  # 정상 반환 (저장은 건너뜀)


# ---------------------------------------------------------------------------
# 6. 빈 리스트는 저장 건너뜀
# ---------------------------------------------------------------------------


async def test_save_candles_empty_list_returns_zero(db_session: AsyncSession) -> None:
    svc = MarketDataService(FakeBroker(), db_session)
    saved = await svc.save_candles("005930", "1m", [])
    assert saved == 0
    rows = (await db_session.execute(select(MarketData))).scalars().all()
    assert rows == []
