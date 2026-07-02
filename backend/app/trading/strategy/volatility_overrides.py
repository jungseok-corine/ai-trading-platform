"""변동성 레짐별 파라미터 오버라이드 (C-6.4).

사람이 승인한 StrategyVersion.parameters 안의 `volatility_overrides`를,
현재 인트라데이 레짐(C-6.3)에 맞춰 **런타임에만** 적용한다.

원칙:
- 버전 원본 파라미터는 절대 수정하지 않는다 (런타임 dict 병합만).
- 밴드(오버라이드 값)는 버전 승인 시 사람이 함께 승인한 것 — AI가 임의 값을 만들지 않는다.
- 안전 관련 키는 오버라이드 불가(BLOCKED_KEYS) — 레짐이 자동매매를 켜거나
  계좌/전략을 바꾸는 일은 구조적으로 불가능하다.

예:
    "volatility_overrides": {
        "elevated": {"cash_pct": 5, "stop_loss_pct": 1.5},
        "extreme": {"cash_pct": 2, "stop_loss_pct": 1.0}
    }
"""
from __future__ import annotations

from typing import Any

# 레짐 오버라이드로 절대 바꿀 수 없는 키 — 자동매매 토글/계좌/전략 정체성/유니버스 경계.
BLOCKED_KEYS = frozenset(
    {
        "auto_trade_enabled",
        "universe_auto_trade",
        "account_id",
        "enabled",
        "strategy_type",
        "universe",
        "universe_market",
        "max_orders_per_run",
        "market",
        "exchange",
        "symbol_code",
        "volatility_overrides",
    }
)

VALID_REGIME_KEYS = frozenset({"calm", "normal", "elevated", "extreme"})


def apply_volatility_overrides(
    params: dict[str, Any],
    overrides: dict[str, Any] | None,
    regime: str,
) -> tuple[dict[str, Any], list[str]]:
    """현재 레짐의 오버라이드를 적용한 (새 dict, 적용된 키 목록)을 반환한다.

    - overrides가 없거나 레짐 항목이 없으면 원본 params 그대로 (적용 키 []).
    - BLOCKED_KEYS는 조용히 무시하지 않고 적용 목록에서 제외한다(원본 값 유지).
    - 입력 params는 변경하지 않는다.
    """
    if not isinstance(overrides, dict) or not overrides:
        return params, []
    regime_overrides = overrides.get(regime)
    if not isinstance(regime_overrides, dict) or not regime_overrides:
        return params, []

    effective = dict(params)
    applied: list[str] = []
    for key, value in regime_overrides.items():
        if key in BLOCKED_KEYS:
            continue
        effective[key] = value
        applied.append(key)
    if not applied:
        return params, []
    return effective, sorted(applied)


def validate_volatility_overrides(overrides: dict[str, Any]) -> None:
    """스키마 검증용: 레짐 키/차단 키를 확인하고 위반 시 ValueError."""
    for regime_key, regime_overrides in overrides.items():
        if regime_key not in VALID_REGIME_KEYS:
            raise ValueError(
                f"volatility_overrides의 레짐 키 {regime_key!r}는 유효하지 않습니다. "
                f"허용값: {sorted(VALID_REGIME_KEYS)}"
            )
        if not isinstance(regime_overrides, dict):
            raise ValueError(f"volatility_overrides[{regime_key!r}]는 dict여야 합니다.")
        blocked = sorted(set(regime_overrides) & BLOCKED_KEYS)
        if blocked:
            raise ValueError(
                f"volatility_overrides[{regime_key!r}]에 오버라이드 불가 키가 있습니다: {blocked}"
            )
