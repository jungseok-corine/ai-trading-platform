"""Phase A: 시장 세션 판단 + 러너 세션 게이팅."""
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.market_session import (
    MarketPhase,
    is_closing_auction,
    is_signal_active,
    kr_market_phase,
    us_market_phase,
)
from app.common.timezone import KST
from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.strategy import Strategy, StrategyVersion
from app.services.market_data_service import MarketDataService
from app.services.signal_service import SignalService
from app.services.strategy_runner_service import StrategyRunnerService

from tests.test_strategy_runner_service import FakeBrokerClient, _make_candles

# 2026-06-22는 월요일.
_MON = lambda h, m: datetime(2026, 6, 22, h, m, tzinfo=KST)  # noqa: E731
_SAT = lambda h, m: datetime(2026, 6, 20, h, m, tzinfo=KST)  # noqa: E731


# --------------------------------------------------------------------------- #
# KR 세션
# --------------------------------------------------------------------------- #


def test_kr_phases() -> None:
    assert kr_market_phase(_MON(8, 15)) == MarketPhase.PRE      # NXT 프리(08:00~)
    assert kr_market_phase(_MON(8, 45)) == MarketPhase.PRE
    assert kr_market_phase(_MON(11, 0)) == MarketPhase.REGULAR
    assert kr_market_phase(_MON(15, 25)) == MarketPhase.CLOSING_AUCTION
    assert kr_market_phase(_MON(16, 30)) == MarketPhase.POST
    assert kr_market_phase(_MON(19, 0)) == MarketPhase.POST     # NXT 애프터(~20:00)
    assert kr_market_phase(_MON(21, 29)) == MarketPhase.CLOSED  # 캡처의 그 시각
    assert kr_market_phase(_SAT(11, 0)) == MarketPhase.CLOSED   # 주말


def test_extended_session_gate() -> None:
    # 확장 off: 애프터(POST)/프리는 비활성
    assert is_signal_active("KR", _MON(18, 0)) is False
    assert is_signal_active("KR", _MON(8, 15)) is False
    # 확장 on: 프리/애프터(NXT 시간대 포함) 활성
    assert is_signal_active("KR", _MON(18, 0), include_extended=True) is True   # NXT 애프터
    assert is_signal_active("KR", _MON(8, 15), include_extended=True) is True   # NXT 프리
    assert is_signal_active("KR", _MON(21, 0), include_extended=True) is False  # 20시 이후 휴장
    # US 확장: 22:00 KST = 09:00 EDT → 프리마켓
    assert is_signal_active("US", _MON(22, 0)) is False
    assert is_signal_active("US", _MON(22, 0), include_extended=True) is True


async def test_runner_extended_session_generates_signal(
    db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(
        "app.services.strategy_runner_service.get_settings",
        lambda: SimpleNamespace(
            strategy_session_gating_enabled=True, signal_extended_sessions_enabled=True
        ),
    )
    await _create_version(db_session)
    broker = FakeBrokerClient({"005930": _make_candles([100] * 20 + [200])})
    runner = _runner(db_session, broker)

    # 확장 세션 켜짐 + 애프터(18:00) → 신호 생성(국장 NXT 시간대 가정)
    results = await runner.run_once(now=_MON(18, 0))
    assert len(results) == 1
    assert results[0].signal_created is True


def test_kr_signal_active_and_closing() -> None:
    assert is_signal_active("KR", _MON(11, 0)) is True
    assert is_signal_active("KR", _MON(15, 25)) is True   # 종가 동시호가도 활성
    assert is_signal_active("KR", _MON(21, 29)) is False
    assert is_closing_auction("KR", _MON(15, 25)) is True
    assert is_closing_auction("KR", _MON(11, 0)) is False


# --------------------------------------------------------------------------- #
# US 세션 (ET 변환, 서머타임 자동)
# --------------------------------------------------------------------------- #


def test_us_phases_via_et() -> None:
    # 2026-06-22 23:30 KST = 10:30 EDT → 정규장
    assert us_market_phase(_MON(23, 30)) == MarketPhase.REGULAR
    assert is_signal_active("US", _MON(23, 30)) is True
    # 2026-06-22 11:00 KST = 22:00 EDT(전일) → 휴장
    assert us_market_phase(_MON(11, 0)) == MarketPhase.CLOSED
    assert is_signal_active("US", _MON(11, 0)) is False
    # 같은 11:00 KST라도 KR은 정규장 — 시장별로 다르게 동작
    assert is_signal_active("KR", _MON(11, 0)) is True


# --------------------------------------------------------------------------- #
# 러너 세션 게이팅
# --------------------------------------------------------------------------- #

_PARAMS = {
    "strategy_type": "moving_average_cross",
    "symbol_code": "005930",
    "short_window": 5,
    "long_window": 20,
    "quantity": 1,
    "enabled": True,
    "market": "KR",
}


async def _create_version(session: AsyncSession) -> StrategyVersion:
    strategy = Strategy(name="session gate test", description="t")
    session.add(strategy)
    await session.flush()
    version = StrategyVersion(
        strategy_id=strategy.id, version_no=1, parameters=_PARAMS,
        status=StrategyVersionStatus.ACTIVE,
    )
    session.add(version)
    await session.flush()
    return version


def _runner(session: AsyncSession, broker: FakeBrokerClient) -> StrategyRunnerService:
    return StrategyRunnerService(session, SignalService(session, MarketDataService(broker)))


async def test_runner_skips_when_kr_market_closed(db_session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.strategy_runner_service.get_settings",
        lambda: SimpleNamespace(strategy_session_gating_enabled=True, signal_extended_sessions_enabled=False),
    )
    await _create_version(db_session)
    broker = FakeBrokerClient({"005930": _make_candles([100] * 20 + [200])})  # 골든크로스 → 매수
    runner = _runner(db_session, broker)

    # 장 마감 후(21:29) → 세션 비활성 → 신호 없음
    closed = await runner.run_once(now=_MON(21, 29))
    assert closed == []

    # 정규장(11:00) → 신호 생성
    opened = await runner.run_once(now=_MON(11, 0))
    assert len(opened) == 1
    assert opened[0].signal_created is True


async def test_gating_disabled_runs_regardless_of_time(db_session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.strategy_runner_service.get_settings",
        lambda: SimpleNamespace(strategy_session_gating_enabled=False, signal_extended_sessions_enabled=False),
    )
    await _create_version(db_session)
    broker = FakeBrokerClient({"005930": _make_candles([100] * 20 + [200])})
    runner = _runner(db_session, broker)

    # 게이팅 꺼져 있으면 장 마감 시각이어도 동작(기존 동작 보존)
    results = await runner.run_once(now=_MON(21, 29))
    assert len(results) == 1
    assert results[0].signal_created is True


# --------------------------------------------------------------------------- #
# Phase B: 종가 매도 결정 (exit_on_close)
# --------------------------------------------------------------------------- #

_EXIT_PARAMS = {**_PARAMS, "exit_on_close": True}


async def _create_exit_version(session: AsyncSession) -> StrategyVersion:
    strategy = Strategy(name="exit on close", description="t")
    session.add(strategy)
    await session.flush()
    version = StrategyVersion(
        strategy_id=strategy.id, version_no=1, parameters=_EXIT_PARAMS,
        status=StrategyVersionStatus.ACTIVE,
    )
    session.add(version)
    await session.flush()
    return version


async def test_exit_on_close_emits_sell_during_closing_auction(
    db_session: AsyncSession, monkeypatch
) -> None:
    from sqlalchemy import select

    from app.domain.models.enums import TradeSide
    from app.domain.models.signal_log import SignalLog

    monkeypatch.setattr(
        "app.services.strategy_runner_service.get_settings",
        lambda: SimpleNamespace(strategy_session_gating_enabled=True, signal_extended_sessions_enabled=False),
    )
    await _create_exit_version(db_session)
    # 단조 상승 캔들 — 정규장이라면 골든크로스 매수가 났을 데이터.
    broker = FakeBrokerClient({"005930": _make_candles([100] * 20 + [200])})
    runner = _runner(db_session, broker)

    # 종가 동시호가(15:25) → 일반 신호 대신 '종가 청산' 매도가 나야 한다.
    results = await runner.run_once(now=_MON(15, 25))
    assert len(results) == 1
    assert results[0].signal_created is True

    rows = (await db_session.execute(select(SignalLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].signal_type == TradeSide.SELL
    assert "종가 청산" in rows[0].reason


async def test_exit_on_close_inactive_during_regular_session(
    db_session: AsyncSession, monkeypatch
) -> None:
    from sqlalchemy import select

    from app.domain.models.enums import TradeSide
    from app.domain.models.signal_log import SignalLog

    monkeypatch.setattr(
        "app.services.strategy_runner_service.get_settings",
        lambda: SimpleNamespace(strategy_session_gating_enabled=True, signal_extended_sessions_enabled=False),
    )
    await _create_exit_version(db_session)
    broker = FakeBrokerClient({"005930": _make_candles([100] * 20 + [200])})
    runner = _runner(db_session, broker)

    # 정규장(11:00) → 종가 청산 아님, 평소 전략 신호(골든크로스 매수)가 나야 한다.
    await runner.run_once(now=_MON(11, 0))
    rows = (await db_session.execute(select(SignalLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].signal_type == TradeSide.BUY
