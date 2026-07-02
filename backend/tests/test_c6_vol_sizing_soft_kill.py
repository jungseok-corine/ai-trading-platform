"""C-6.5: 변동성 사이징(vol_scaled) + soft kill 리스크 룰.

안전 검증: soft kill 기본 off, SELL(청산)은 어떤 레짐에서도 차단되지 않음,
기존 포지션 강제 축소 없음(신규 BUY 차단만).
"""
from decimal import Decimal

import pydantic
import pytest

from app.core.config import Settings
from app.domain.models.enums import TradeSide
from app.domain.models.risk import RiskConfig
from app.trading.pricing.sizing import VALID_QUANTITY_MODES, compute_order_quantity
from app.trading.risk.context import RiskContext
from app.trading.risk.rules import DEFAULT_RULES, VolatilitySoftKillRule
from app.trading.strategy.base import Signal
from app.trading.strategy.schemas import StrategyVersionParameters

# ── vol_scaled 사이징 ──────────────────────────────────────────────────


def test_vol_scaled_mode_registered():
    assert "vol_scaled" in VALID_QUANTITY_MODES


def test_vol_scaled_full_multiplier_equals_cash_pct():
    qty = compute_order_quantity(
        mode="vol_scaled", fixed_quantity=1, price=Decimal("10000"),
        cash_pct=10, available_cash=Decimal("1000000"), vol_multiplier=1.0,
    )
    # 1,000,000 × 10% / 10,000 = 10주
    assert qty == 10


def test_vol_scaled_reduces_budget_by_multiplier():
    qty = compute_order_quantity(
        mode="vol_scaled", fixed_quantity=1, price=Decimal("10000"),
        cash_pct=10, available_cash=Decimal("1000000"), vol_multiplier=0.25,
    )
    # 예산 100,000 × 0.25 = 25,000 → 2주
    assert qty == 2


def test_vol_scaled_fallback_to_fixed_without_cash_info():
    qty = compute_order_quantity(
        mode="vol_scaled", fixed_quantity=3, price=Decimal("10000"),
        cash_pct=10, available_cash=None, vol_multiplier=0.5,
    )
    assert qty == 3


def test_vol_scaled_zero_when_budget_below_one_share():
    qty = compute_order_quantity(
        mode="vol_scaled", fixed_quantity=1, price=Decimal("100000"),
        cash_pct=1, available_cash=Decimal("1000000"), vol_multiplier=0.25,
    )
    # 예산 10,000 × 0.25 = 2,500 < 100,000 → 0주 (주문 건너뜀)
    assert qty == 0


# ── 스키마 ─────────────────────────────────────────────────────────────

_BASE = {"strategy_type": "moving_average_cross", "symbol_code": "005930"}


def test_schema_accepts_vol_scaled_with_cash_pct():
    p = StrategyVersionParameters(**_BASE, quantity_mode="vol_scaled", cash_pct=10)
    assert p.quantity_mode == "vol_scaled"


def test_schema_rejects_vol_scaled_without_cash_pct():
    with pytest.raises(pydantic.ValidationError, match="vol_scaled"):
        StrategyVersionParameters(**_BASE, quantity_mode="vol_scaled")


# ── soft kill 룰 ────────────────────────────────────────────────────────


def _context(regime: str | None) -> RiskContext:
    return RiskContext(
        account_id=1,
        account_balance=Decimal("1000000"),
        today_realized_pnl=Decimal("0"),
        today_trade_count=0,
        open_positions_count=0,
        consecutive_losses=0,
        intraday_regime=regime,
    )


def _signal(side: TradeSide) -> Signal:
    return Signal(
        symbol_code="005930", side=side, quantity=1,
        price=Decimal("10000"), reason="test",
    )


def _config() -> RiskConfig:
    return RiskConfig(
        account_id=1, max_daily_loss_amount=Decimal("100000"),
        max_position_size=Decimal("1000000"), max_open_positions=10,
        max_trades_per_day=100, consecutive_loss_limit=10, emergency_stop=False,
    )


def test_soft_kill_blocks_buy_in_extreme_regime():
    result = VolatilitySoftKillRule().check(_signal(TradeSide.BUY), _config(), _context("extreme"))
    assert result.approved is False
    assert result.rule_name == "volatility_soft_kill"


def test_soft_kill_allows_sell_in_extreme_regime():
    """청산(SELL)은 extreme에서도 차단하지 않는다 — 위험을 줄이는 주문."""
    result = VolatilitySoftKillRule().check(_signal(TradeSide.SELL), _config(), _context("extreme"))
    assert result.approved is True


@pytest.mark.parametrize("regime", ["calm", "normal", "elevated", "unknown", None])
def test_soft_kill_allows_buy_in_non_extreme_regimes(regime):
    result = VolatilitySoftKillRule().check(_signal(TradeSide.BUY), _config(), _context(regime))
    assert result.approved is True


def test_soft_kill_rule_in_default_rules():
    assert any(isinstance(r, VolatilitySoftKillRule) for r in DEFAULT_RULES)


# ── 안전 불변식 ─────────────────────────────────────────────────────────


def test_soft_kill_disabled_by_default():
    """코드 기본값: soft kill 게이트 off → RiskContext.intraday_regime=None → 룰 통과."""
    s = Settings(_env_file=None)
    assert s.volatility_soft_kill_enabled is False
    # 기본 컨텍스트(regime None)에서 BUY는 통과
    result = VolatilitySoftKillRule().check(_signal(TradeSide.BUY), _config(), _context(None))
    assert result.approved is True
