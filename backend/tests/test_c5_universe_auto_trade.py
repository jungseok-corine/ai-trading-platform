"""C-5.19: 유니버스 자동매매(안전장치) — 명시 옵트인 + 모의계좌 전용 + 회당 주문 상한."""
import pydantic
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, StrategyVersionStatus
from app.domain.models.risk import RiskConfig
from app.domain.models.watchlist import Watchlist, WatchlistSymbol
from app.trading.strategy.schemas import StrategyVersionParameters

from decimal import Decimal

from tests.test_strategy_runner_auto_trade import (
    FakeBrokerClient,
    _create_strategy_version,
    _make_candles,
    _runner,
)

_BASE = {
    "strategy_type": "moving_average_cross",
    "universe": "watchlist",
    "short_window": 5,
    "long_window": 20,
    "quantity": 1,
    "enabled": True,
}


async def _watchlist(session: AsyncSession, symbols: list[str]) -> None:
    wl = Watchlist(name="t", enabled=True)
    session.add(wl)
    await session.flush()
    for s in symbols:
        session.add(WatchlistSymbol(watchlist_id=wl.id, symbol_code=s, market="KR", enabled=True))
    await session.commit()


async def _account(session: AsyncSession, account_type: AccountType) -> Account:
    acc = Account(account_type=account_type, broker_account_no="00000000-01")
    session.add(acc)
    await session.flush()
    session.add(RiskConfig(
        account_id=acc.id, max_daily_loss_amount=Decimal("100000"),
        max_position_size=Decimal("1000000"), max_open_positions=10,
        max_trades_per_day=10, consecutive_loss_limit=3, emergency_stop=False,
    ))
    await session.flush()
    return acc


def _broker(symbols: list[str]) -> FakeBrokerClient:
    golden = _make_candles([100] * 20 + [200])
    return FakeBrokerClient({s: golden for s in symbols})


# --------------------------------------------------------------------------- #
# 러너 동작
# --------------------------------------------------------------------------- #


async def test_universe_auto_trade_paper_places_orders(db_session: AsyncSession) -> None:
    acc = await _account(db_session, AccountType.PAPER)
    await _watchlist(db_session, ["005930", "000660"])
    broker = _broker(["005930", "000660"])
    await _create_strategy_version(db_session, {
        **_BASE, "universe_auto_trade": True, "account_id": acc.id, "max_orders_per_run": 5,
    })

    results = await _runner(db_session, broker).run_once()

    assert sum(1 for r in results if r.trade_attempted) == 2  # 두 종목 모두 자동매매
    assert len(broker.place_order_calls) == 2


async def test_universe_auto_trade_blocked_on_live_account(db_session: AsyncSession) -> None:
    acc = await _account(db_session, AccountType.LIVE)  # 실계좌 → 모의 전용 가드로 차단
    await _watchlist(db_session, ["005930", "000660"])
    broker = _broker(["005930", "000660"])
    await _create_strategy_version(db_session, {
        **_BASE, "universe_auto_trade": True, "account_id": acc.id,
    })

    results = await _runner(db_session, broker).run_once()

    assert all(not r.trade_attempted for r in results)  # 신호만, 주문 없음
    assert broker.place_order_calls == []
    assert all(r.signal_created for r in results)  # 신호는 생성됨


async def test_universe_auto_trade_per_run_cap(db_session: AsyncSession) -> None:
    acc = await _account(db_session, AccountType.PAPER)
    await _watchlist(db_session, ["005930", "000660", "035720"])
    broker = _broker(["005930", "000660", "035720"])
    await _create_strategy_version(db_session, {
        **_BASE, "universe_auto_trade": True, "account_id": acc.id, "max_orders_per_run": 2,
    })

    results = await _runner(db_session, broker).run_once()

    # 3종목 신호가 떠도 회당 상한 2건만 주문, 나머지는 신호만.
    assert sum(1 for r in results if r.trade_attempted) == 2
    assert len(broker.place_order_calls) == 2
    assert sum(1 for r in results if r.signal_created) == 3


async def test_universe_without_opt_in_is_signal_only(db_session: AsyncSession) -> None:
    acc = await _account(db_session, AccountType.PAPER)
    await _watchlist(db_session, ["005930"])
    broker = _broker(["005930"])
    # universe_auto_trade 미설정(기본 off) → 신호만
    await _create_strategy_version(db_session, {**_BASE, "account_id": acc.id})

    results = await _runner(db_session, broker).run_once()

    assert all(not r.trade_attempted for r in results)
    assert broker.place_order_calls == []


# --------------------------------------------------------------------------- #
# 스키마 검증
# --------------------------------------------------------------------------- #


def test_schema_universe_auto_trade_requires_account_id() -> None:
    StrategyVersionParameters(
        strategy_type="moving_average_cross", universe="watchlist",
        universe_auto_trade=True, account_id=1,
    )  # ok
    with pytest.raises(pydantic.ValidationError):
        StrategyVersionParameters(
            strategy_type="moving_average_cross", universe="watchlist",
            universe_auto_trade=True,  # account_id 없음
        )


def test_schema_universe_auto_trade_requires_universe() -> None:
    with pytest.raises(pydantic.ValidationError):
        StrategyVersionParameters(
            strategy_type="moving_average_cross", symbol_code="005930",
            universe_auto_trade=True,  # 유니버스 아님
        )
