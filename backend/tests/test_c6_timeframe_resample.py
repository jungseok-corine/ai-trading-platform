"""C-6.18: KR timeframe 버그 수정 — 1분봉 리샘플 + 일봉 지원 + 캐시 키 분리.

배경: KR 경로가 timeframe을 무시하고 항상 1분봉을 반환해, 모든 '5m' 전략이
사실상 1분봉 위에서 돌았고 market_data '5m' 행도 1분 간격으로 저장돼 있었다.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.market_data import MarketData
from app.services.market_data_service import MarketDataService, resample_candles
from app.trading.broker.schemas import DailyCandle, MinuteCandle


def _c(date: str, hhmm: str, o: int, h: int, lo: int, c: int, v: int = 100) -> MinuteCandle:
    return MinuteCandle(
        business_date=date, trade_time=hhmm + "00",
        open_price=Decimal(o), high_price=Decimal(h),
        low_price=Decimal(lo), close_price=Decimal(c), volume=v,
    )


# ── resample_candles 순수 함수 ──────────────────────────────────────────


def test_resample_5m_aggregates_ohlcv():
    candles = [
        _c("20260703", "0900", 100, 105, 99, 101),
        _c("20260703", "0901", 101, 110, 100, 108),
        _c("20260703", "0902", 108, 109, 104, 105),
        _c("20260703", "0903", 105, 106, 103, 104),
        _c("20260703", "0904", 104, 107, 104, 106),
        _c("20260703", "0905", 106, 111, 106, 110),  # 다음 버킷
    ]
    out = resample_candles(candles, 5)
    assert len(out) == 2
    b1 = out[0]
    assert b1.trade_time == "090000"
    assert b1.open_price == 100 and b1.close_price == 106
    assert b1.high_price == 110 and b1.low_price == 99
    assert b1.volume == 500
    assert out[1].trade_time == "090500"
    assert out[1].open_price == 106


def test_resample_1m_is_identity():
    candles = [_c("20260703", "0900", 100, 101, 99, 100)]
    assert resample_candles(candles, 1) is candles


def test_resample_crosses_day_boundary():
    candles = [
        _c("20260702", "1529", 100, 101, 99, 100),
        _c("20260703", "0900", 102, 103, 101, 102),
    ]
    out = resample_candles(candles, 5)
    assert len(out) == 2  # 날짜가 다르면 같은 버킷으로 합치지 않는다


# ── KR 경로 통합 (fake broker) ──────────────────────────────────────────


class _FakeBroker:
    """당일 최근 1분봉 12개를 돌려주는 국내 브로커 대역."""

    def __init__(self) -> None:
        base = datetime(2026, 7, 3, 9, 30)
        self.minute = [
            _c("20260703", (base + timedelta(minutes=i)).strftime("%H%M"), 100 + i, 101 + i, 99 + i, 100 + i)
            for i in range(12)
        ]
        self.daily = [
            DailyCandle(
                business_date=f"202606{d:02d}", open_price=Decimal(100 + d),
                high_price=Decimal(105 + d), low_price=Decimal(95 + d),
                close_price=Decimal(102 + d), volume=1000,
            )
            for d in range(1, 26)
        ]

    async def get_minute_candles(self, symbol_code, target_time=None, include_past_data=True):
        return list(self.minute)

    async def get_daily_candles(self, symbol_code, count=252, **kwargs):
        return list(reversed(self.daily))[: count]


@pytest.mark.asyncio
async def test_kr_5m_returns_5min_spacing(db_session: AsyncSession):
    """핵심 버그 수정 검증: timeframe=5m이면 5분 간격 캔들이 나온다."""
    svc = MarketDataService(broker=_FakeBroker(), session=db_session)
    candles = await svc.get_recent_candles("TEST01", count=10, timeframe="5m")
    assert len(candles) >= 2
    times = [int(c.trade_time[:4]) for c in candles]
    # 5분 버킷 시작 시각 — 분이 5의 배수
    assert all(t % 5 == 0 for t in times)


@pytest.mark.asyncio
async def test_kr_5m_merges_db_history(db_session: AsyncSession):
    """DB에 축적된 1m 이력이 리샘플 재료로 병합된다 (추가 KIS 호출 없이 긴 창 확보)."""
    now = datetime.now(timezone.utc)
    for i in range(60):  # fresh(12개)보다 오래된 1시간 전 구간
        ts = now - timedelta(minutes=180 - i)
        db_session.add(
            MarketData(
                symbol_code="TEST01", timeframe="1m", ts=ts,
                open=Decimal(90), high=Decimal(91), low=Decimal(89), close=Decimal(90), volume=50,
            )
        )
    await db_session.commit()

    svc = MarketDataService(broker=_FakeBroker(), session=db_session)
    candles = await svc.get_recent_candles("TEST01", count=30, timeframe="5m")
    # fresh 12개(≈3버킷)만으론 30개를 못 채운다 — DB 병합으로 더 많은 5m 버킷 확보
    assert len(candles) > 3


@pytest.mark.asyncio
async def test_kr_1m_saves_raw_and_unchanged(db_session: AsyncSession):
    svc = MarketDataService(broker=_FakeBroker(), session=db_session)
    candles = await svc.get_recent_candles("TEST02", count=10, timeframe="1m")
    assert len(candles) == 10
    times = [int(c.trade_time[:4]) for c in candles]
    assert times == sorted(times)


@pytest.mark.asyncio
async def test_kr_daily_timeframe(db_session: AsyncSession):
    """timeframe=1d — 일봉이 MinuteCandle 형태(153000)로 변환된다."""
    svc = MarketDataService(broker=_FakeBroker(), session=db_session)
    candles = await svc.get_recent_candles("TEST03", count=20, timeframe="1d")
    assert len(candles) == 20
    assert all(c.trade_time == "153000" for c in candles)
    dates = [c.business_date for c in candles]
    assert dates == sorted(dates)


# ── 캐시 키 분리 ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_candle_cache_separates_timeframes(db_session: AsyncSession):
    """1m 전략의 캐시를 5m 전략이 받지 않는다 (교차 오염 수정)."""
    from app.services.signal_service import SignalService
    from app.trading.strategy.registry import create_strategy

    svc = SignalService(db_session, MarketDataService(broker=_FakeBroker(), session=db_session))
    strategy = create_strategy("moving_average_cross", {"short_window": 2, "long_window": 3})
    cache: dict = {}
    await svc.generate_and_log_signal(
        strategy, "TEST04", None, strategy_params={"timeframe": "1m"}, candle_cache=cache
    )
    await svc.generate_and_log_signal(
        strategy, "TEST04", None, strategy_params={"timeframe": "5m"}, candle_cache=cache
    )
    assert ("TEST04", "1m") in cache and ("TEST04", "5m") in cache
    tf1 = {c.trade_time for c in cache[("TEST04", "1m")]}
    tf5 = {c.trade_time for c in cache[("TEST04", "5m")]}
    assert tf1 != tf5
