"""장 마감/휴장 후 스테일 캔들로 인한 허위 신호 방지 — 캔들 신선도 가드.

배경: 국장 마감(15:30) 후에도 KIS 분봉 API는 마지막(또는 종가로 평탄한) 캔들을 계속
돌려준다. 이때 RSI가 100으로 계산되어 모든 종목에 허위 매도 신호가 찍히는 문제가 있었다.
가드는 최신 캔들이 너무 오래되면 신호 생성을 건너뛴다(시장 인지: KR/US 무관, 데이터 기준).
"""
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.enums import StrategyVersionStatus
from app.services.market_data_service import MarketDataService
from app.services.signal_service import (
    SignalService,
    _is_candle_stale,
    _latest_candle_age_minutes,
)
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.rsi_reversion import RsiReversionStrategy

from tests.test_strategy_runner_service import FakeBrokerClient


def _candles_ending_at(last_dt: datetime, closes: list[int]) -> list[MinuteCandle]:
    """closes(오래된 순)로 1분 간격 캔들을 만들되, 마지막 캔들 시각을 last_dt로 맞춘다."""
    n = len(closes)
    out: list[MinuteCandle] = []
    for i, close in enumerate(closes):
        ts = last_dt - timedelta(minutes=(n - 1 - i))
        price = Decimal(str(close))
        out.append(MinuteCandle(
            business_date=ts.strftime("%Y%m%d"),
            trade_time=ts.strftime("%H%M%S"),
            open_price=price, high_price=price, low_price=price,
            close_price=price, volume=1000,
        ))
    return out


# --------------------------------------------------------------------------- #
# 순수 함수
# --------------------------------------------------------------------------- #


def test_latest_candle_age_minutes() -> None:
    now = datetime(2026, 6, 22, 21, 29, tzinfo=KST)
    candles = _candles_ending_at(datetime(2026, 6, 22, 15, 30, tzinfo=KST), [100] * 16)
    age = _latest_candle_age_minutes(candles, now)
    assert age is not None
    assert abs(age - (5 * 60 + 59)) < 0.01  # 15:30 → 21:29 = 359분


def test_stale_when_old_and_fresh_when_recent() -> None:
    now = datetime(2026, 6, 22, 21, 29, tzinfo=KST)
    # 장 마감(15:30) 캔들 — 6시간 가까이 지남 → stale
    stale = _candles_ending_at(datetime(2026, 6, 22, 15, 30, tzinfo=KST), list(range(100, 116)))
    assert _is_candle_stale(stale, "1m", now, max_staleness_minutes=15) is True
    # 방금 전 캔들 → fresh
    fresh = _candles_ending_at(now - timedelta(minutes=1), list(range(100, 116)))
    assert _is_candle_stale(fresh, "1m", now, max_staleness_minutes=15) is False


def test_guard_disabled_when_threshold_zero() -> None:
    now = datetime(2026, 6, 22, 21, 29, tzinfo=KST)
    stale = _candles_ending_at(datetime(2026, 6, 22, 15, 30, tzinfo=KST), [100] * 16)
    assert _is_candle_stale(stale, "1m", now, max_staleness_minutes=0) is False


def test_threshold_respects_timeframe() -> None:
    now = datetime(2026, 6, 22, 12, 0, tzinfo=KST)
    # 30분봉: 임계치 = max(15, 30*3=90)분. 60분 전 캔들은 fresh여야 한다.
    candles = _candles_ending_at(now - timedelta(minutes=60), list(range(100, 116)))
    assert _is_candle_stale(candles, "30m", now, max_staleness_minutes=15) is False
    # 같은 캔들이 1분봉 기준(임계치 15분)에서는 stale
    assert _is_candle_stale(candles, "1m", now, max_staleness_minutes=15) is True


# --------------------------------------------------------------------------- #
# 통합: generate_and_log_signal 가드
# --------------------------------------------------------------------------- #


async def _create_rsi_version(session: AsyncSession) -> StrategyVersion:
    strategy = Strategy(name="rsi stale test", description="t")
    session.add(strategy)
    await session.flush()
    version = StrategyVersion(
        strategy_id=strategy.id, version_no=1,
        parameters={"strategy_type": "rsi_reversion", "rsi_period": 14},
        status=StrategyVersionStatus.ACTIVE,
    )
    session.add(version)
    await session.flush()
    return version


async def test_stale_candles_skip_signal_but_fresh_create(
    db_session: AsyncSession, monkeypatch
) -> None:
    """동일한 RSI=100(단조 상승) 데이터라도 캔들이 stale이면 신호를 만들지 않는다."""
    # 가드 활성화(설정값 주입)
    monkeypatch.setattr(
        "app.services.signal_service.get_settings",
        lambda: SimpleNamespace(signal_max_candle_staleness_minutes=15),
    )
    version = await _create_rsi_version(db_session)
    now = datetime.now(KST)
    rising = list(range(100, 116))  # 단조 상승 → RSI=100 → 매도 신호 후보

    # 1) stale 캔들(장 마감 시각) → 신호 없음
    stale_broker = FakeBrokerClient({"005930": _candles_ending_at(
        now.replace(hour=15, minute=30, second=0, microsecond=0) - timedelta(days=1), rising
    )})
    svc = SignalService(db_session, MarketDataService(stale_broker))
    log = await svc.generate_and_log_signal(
        RsiReversionStrategy.from_params({"rsi_period": 14}), "005930", version.id,
        strategy_params={"timeframe": "1m"},
    )
    assert log is None
    rows = (await db_session.execute(select(SignalLog))).scalars().all()
    assert rows == []

    # 2) fresh 캔들(방금 전) → 매도 신호 생성
    fresh_broker = FakeBrokerClient({"005930": _candles_ending_at(now - timedelta(minutes=1), rising)})
    svc2 = SignalService(db_session, MarketDataService(fresh_broker))
    log2 = await svc2.generate_and_log_signal(
        RsiReversionStrategy.from_params({"rsi_period": 14}), "005930", version.id,
        strategy_params={"timeframe": "1m"},
    )
    assert log2 is not None
    assert log2.signal_type.value == "sell"
