"""C-6.4: 변동성 레짐별 파라미터 오버라이드 — 밴드 내 자동 전환.

안전 검증: 차단 키(자동매매 토글/계좌 등)는 어떤 레짐에서도 오버라이드 불가,
버전 원본 파라미터는 런타임에 수정되지 않는다.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pydantic
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.market_data import MarketData
from app.domain.models.signal_log import SignalLog
from app.services.intraday_regime_service import clear_regime_cache
from app.trading.strategy.schemas import StrategyVersionParameters
from app.trading.strategy.volatility_overrides import (
    BLOCKED_KEYS,
    apply_volatility_overrides,
)

# ── 순수 함수 단위 테스트 ────────────────────────────────────────────────


def test_apply_returns_original_when_no_overrides():
    params = {"short_window": 5, "cash_pct": 10}
    effective, applied = apply_volatility_overrides(params, None, "elevated")
    assert effective is params
    assert applied == []


def test_apply_returns_original_when_regime_not_defined():
    params = {"cash_pct": 10}
    overrides = {"extreme": {"cash_pct": 2}}
    effective, applied = apply_volatility_overrides(params, overrides, "normal")
    assert effective is params
    assert applied == []


def test_apply_merges_regime_overrides_without_mutating_original():
    params = {"cash_pct": 10, "stop_loss_pct": 3.0, "short_window": 5}
    overrides = {"elevated": {"cash_pct": 5, "stop_loss_pct": 1.5}}
    effective, applied = apply_volatility_overrides(params, overrides, "elevated")
    assert applied == ["cash_pct", "stop_loss_pct"]
    assert effective["cash_pct"] == 5
    assert effective["stop_loss_pct"] == 1.5
    assert effective["short_window"] == 5
    # 원본 무변경
    assert params["cash_pct"] == 10
    assert params["stop_loss_pct"] == 3.0


def test_apply_blocks_safety_keys():
    """레짐 오버라이드가 자동매매를 켜거나 계좌/전략을 바꿀 수 없다."""
    params = {"auto_trade_enabled": False, "cash_pct": 10}
    overrides = {
        "extreme": {
            "auto_trade_enabled": True,
            "universe_auto_trade": True,
            "account_id": 999,
            "strategy_type": "momentum_surge",
            "enabled": False,
            "cash_pct": 2,
        }
    }
    effective, applied = apply_volatility_overrides(params, overrides, "extreme")
    assert applied == ["cash_pct"]
    assert effective["auto_trade_enabled"] is False
    assert "account_id" not in effective or effective.get("account_id") != 999


def test_apply_all_blocked_returns_original():
    params = {"cash_pct": 10}
    overrides = {"extreme": {"auto_trade_enabled": True}}
    effective, applied = apply_volatility_overrides(params, overrides, "extreme")
    assert effective is params
    assert applied == []


# ── 스키마 검증 테스트 ──────────────────────────────────────────────────

_BASE = {"strategy_type": "moving_average_cross", "symbol_code": "005930"}


def test_schema_accepts_valid_overrides():
    p = StrategyVersionParameters(
        **_BASE,
        volatility_overrides={"elevated": {"cash_pct": 5}, "extreme": {"cash_pct": 2}},
    )
    assert p.volatility_overrides is not None
    assert p.model_dump()["volatility_overrides"]["extreme"]["cash_pct"] == 2


def test_schema_rejects_unknown_regime_key():
    with pytest.raises(pydantic.ValidationError, match="레짐 키"):
        StrategyVersionParameters(
            **_BASE, volatility_overrides={"panic": {"cash_pct": 1}}
        )


def test_schema_rejects_blocked_override_keys():
    with pytest.raises(pydantic.ValidationError, match="오버라이드 불가"):
        StrategyVersionParameters(
            **_BASE, volatility_overrides={"extreme": {"auto_trade_enabled": True}}
        )


# ── 러너 통합 테스트 ────────────────────────────────────────────────────

KST = timezone(timedelta(hours=9))


async def _seed_regime_data(session: AsyncSession, spike: bool) -> None:
    """레짐 판단용 1분봉 3심볼 시드 (spike=True면 extreme 레짐).

    러너는 wall-clock now 기준으로 레짐을 조회하므로 now 기준으로 시드한다.
    """
    now = datetime.now(timezone.utc)
    for sym in ("VR0001", "VR0002", "VR0003"):
        price = 10_000
        for i in range(200):
            ts = now - timedelta(minutes=200 - i)
            rng = 0.06 if (spike and i >= 170) else 0.01
            half = price * rng / 2
            session.add(
                MarketData(
                    symbol_code=sym, timeframe="1m", ts=ts,
                    open=Decimal(price), high=Decimal(price + half),
                    low=Decimal(price - half), close=Decimal(price), volume=1000,
                )
            )
    await session.commit()


@pytest.mark.asyncio
async def test_runner_applies_overrides_and_marks_signal(db_session: AsyncSession):
    """extreme 레짐에서 오버라이드된 파라미터로 신호가 생성되고 reason에 기록된다."""
    from tests.test_strategy_runner_auto_trade import (
        GOLDEN_CROSS_CLOSES,
        FakeBrokerClient,
        _create_strategy_version,
        _make_candles,
        _runner,
    )

    clear_regime_cache()
    await _seed_regime_data(db_session, spike=True)

    # 기본 long_window=150이면 캔들(21개) 부족으로 신호 없음.
    # extreme 오버라이드가 long_window=20으로 낮춰야만 골든크로스 신호가 나온다.
    version = await _create_strategy_version(
        db_session,
        {
            "strategy_type": "moving_average_cross",
            "symbol_code": "005930",
            "short_window": 5,
            "long_window": 150,
            "quantity": 1,
            "timeframe": "1m",
            "enabled": True,
            "auto_trade_enabled": False,
            "volatility_overrides": {"extreme": {"long_window": 20}},
        },
    )
    broker = FakeBrokerClient({"005930": _make_candles(GOLDEN_CROSS_CLOSES)})
    results = await _runner(db_session, broker).run_once()

    created = [r for r in results if r.signal_created]
    assert created, "extreme 오버라이드(long_window=20) 적용 시 신호가 생성돼야 한다"

    log = (
        await db_session.execute(
            select(SignalLog).where(SignalLog.id == created[0].signal_id)
        )
    ).scalar_one()
    assert "변동성 레짐 extreme" in (log.reason or "")
    assert "long_window" in (log.reason or "")

    # 안전: 버전 원본 파라미터는 그대로다.
    await db_session.refresh(version)
    assert version.parameters["long_window"] == 150
    clear_regime_cache()


@pytest.mark.asyncio
async def test_runner_without_overrides_unchanged(db_session: AsyncSession):
    """volatility_overrides가 없으면 레짐 조회 없이 기존 동작 그대로."""
    from tests.test_strategy_runner_auto_trade import (
        GOLDEN_CROSS_CLOSES,
        FakeBrokerClient,
        _create_strategy_version,
        _make_candles,
        _params,
        _runner,
    )

    clear_regime_cache()
    await _create_strategy_version(db_session, _params())
    broker = FakeBrokerClient({"005930": _make_candles(GOLDEN_CROSS_CLOSES)})
    results = await _runner(db_session, broker).run_once()
    created = [r for r in results if r.signal_created]
    assert created

    log = (
        await db_session.execute(
            select(SignalLog).where(SignalLog.id == created[0].signal_id)
        )
    ).scalar_one()
    assert "변동성 레짐" not in (log.reason or "")


@pytest.mark.asyncio
async def test_runner_normal_regime_keeps_base_params(db_session: AsyncSession):
    """레짐이 오버라이드에 정의되지 않았으면(normal) 기본 파라미터 그대로 — 신호 없음."""
    from tests.test_strategy_runner_auto_trade import (
        GOLDEN_CROSS_CLOSES,
        FakeBrokerClient,
        _create_strategy_version,
        _make_candles,
        _runner,
    )

    clear_regime_cache()
    await _seed_regime_data(db_session, spike=False)  # normal 레짐

    await _create_strategy_version(
        db_session,
        {
            "strategy_type": "moving_average_cross",
            "symbol_code": "005930",
            "short_window": 5,
            "long_window": 150,  # 캔들 부족 → 신호 없음 (오버라이드 미적용 확인)
            "quantity": 1,
            "timeframe": "1m",
            "enabled": True,
            "auto_trade_enabled": False,
            "volatility_overrides": {"extreme": {"long_window": 20}},
        },
    )
    broker = FakeBrokerClient({"005930": _make_candles(GOLDEN_CROSS_CLOSES)})
    results = await _runner(db_session, broker).run_once()
    assert all(not r.signal_created for r in results)
    clear_regime_cache()
