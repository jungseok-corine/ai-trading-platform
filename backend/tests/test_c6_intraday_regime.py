"""C-6.3: 인트라데이 변동성 레짐 분류."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.market_data import MarketData
from app.services.intraday_regime_service import (
    REGIME_ELEVATED,
    REGIME_EXTREME,
    REGIME_NORMAL,
    REGIME_UNKNOWN,
    IntradayRegimeService,
    clear_regime_cache,
)

KST = timezone(timedelta(hours=9))
AS_OF = datetime(2026, 6, 30, 14, 0, tzinfo=KST)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_regime_cache()
    yield
    clear_regime_cache()


async def _seed(
    session: AsyncSession,
    symbol: str,
    *,
    bars: int,
    base_range: float,
    recent_range: float | None = None,
    recent_bars: int = 30,
) -> None:
    """1분봉 시드. 마지막 recent_bars 봉의 (high-low) 폭만 recent_range로 바꾼다."""
    price = 10_000
    for i in range(bars):
        ts = AS_OF - timedelta(minutes=bars - i)
        rng = recent_range if (recent_range is not None and i >= bars - recent_bars) else base_range
        half = price * rng / 2
        session.add(
            MarketData(
                symbol_code=symbol,
                timeframe="1m",
                ts=ts,
                open=Decimal(price),
                high=Decimal(price + half),
                low=Decimal(price - half),
                close=Decimal(price),
                volume=1000,
            )
        )
    await session.commit()


@pytest.mark.asyncio
async def test_normal_regime_when_recent_matches_baseline(db_session: AsyncSession):
    for sym in ("RG0001", "RG0002", "RG0003"):
        await _seed(db_session, sym, bars=200, base_range=0.01)

    snap = await IntradayRegimeService(db_session).snapshot(as_of=AS_OF)
    assert snap.regime == REGIME_NORMAL
    assert snap.vol_ratio == pytest.approx(1.0, abs=0.05)
    assert snap.symbols_used == 3


@pytest.mark.asyncio
async def test_extreme_regime_when_recent_vol_spikes(db_session: AsyncSession):
    # 최근 30봉의 변동폭이 기준선의 ~6배 → ratio 급등
    for sym in ("RG0001", "RG0002", "RG0003"):
        await _seed(db_session, sym, bars=200, base_range=0.01, recent_range=0.06)

    snap = await IntradayRegimeService(db_session).snapshot(as_of=AS_OF)
    assert snap.regime == REGIME_EXTREME
    assert snap.vol_ratio is not None and snap.vol_ratio >= 2.5


@pytest.mark.asyncio
async def test_elevated_regime_intermediate_spike(db_session: AsyncSession):
    # 최근 변동폭 ~2배 → ratio가 elevated 구간(1.5~2.5)에 들어온다
    for sym in ("RG0001", "RG0002", "RG0003"):
        await _seed(db_session, sym, bars=200, base_range=0.01, recent_range=0.021)

    snap = await IntradayRegimeService(db_session).snapshot(as_of=AS_OF)
    assert snap.regime == REGIME_ELEVATED


@pytest.mark.asyncio
async def test_unknown_when_insufficient_symbols(db_session: AsyncSession):
    await _seed(db_session, "RG0001", bars=200, base_range=0.01)  # 심볼 1개뿐

    snap = await IntradayRegimeService(db_session).snapshot(as_of=AS_OF)
    assert snap.regime == REGIME_UNKNOWN
    assert snap.vol_ratio is None
    assert "부족" in snap.detail["reason"]


@pytest.mark.asyncio
async def test_unknown_when_no_data(db_session: AsyncSession):
    snap = await IntradayRegimeService(db_session).snapshot(as_of=AS_OF)
    assert snap.regime == REGIME_UNKNOWN
    assert snap.symbols_used == 0


@pytest.mark.asyncio
async def test_explicit_symbols_injection(db_session: AsyncSession):
    """symbols 주입 시 해당 심볼만 사용 (테스트·재현용)."""
    for sym in ("RG0001", "RG0002", "RG0003", "RG0004"):
        await _seed(db_session, sym, bars=200, base_range=0.01)

    snap = await IntradayRegimeService(db_session).snapshot(
        as_of=AS_OF, symbols=["RG0001", "RG0002", "RG0003"]
    )
    assert snap.symbols_used == 3
    assert set(snap.detail["per_symbol_ratio"].keys()) == {"RG0001", "RG0002", "RG0003"}


def test_bundle_prompt_includes_intraday_regime():
    """C-6.11: 번들에 intraday_regime이 있으면 프롬프트에 노출된다."""
    from app.trading.analysis.bundle_prompt import format_bundle_for_prompt

    bundle = {
        "meta": {"symbol_code": "005930", "trading_day": "2026-07-03", "market": "KR"},
        "intraday_regime": {"regime": "extreme", "vol_ratio": 2.8, "symbols_used": 5},
    }
    text = format_bundle_for_prompt(bundle)
    assert "당일 변동성 레짐: extreme" in text
    assert "2.8" in text


def test_bundle_prompt_omits_regime_when_absent():
    from app.trading.analysis.bundle_prompt import format_bundle_for_prompt

    bundle = {"meta": {"symbol_code": "005930", "trading_day": "2026-07-03", "market": "KR"}}
    assert "당일 변동성 레짐" not in format_bundle_for_prompt(bundle)
