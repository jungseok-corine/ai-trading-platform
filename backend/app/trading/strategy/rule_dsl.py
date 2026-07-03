"""전략 DSL — 선언적 JSON 스펙의 검증과 평가 (C-7.1).

LLM/카탈로그가 만든 전략 스펙을 **임의 코드 실행 없이** 해석한다.

스펙 구조 (strategy parameters의 `rule_spec`):
{
  "name": "bollinger_bounce",
  "source": "볼린저 밴드 평균회귀 (John Bollinger)",   # 출처·원리 (사람용)
  "indicators": {
    "bb_lower": {"fn": "bollinger_lower", "period": 20, "num_std": 2.0},
    "rsi14": {"fn": "rsi", "period": 14}
  },
  "entry": {"op": "and", "args": [
    {"op": "lt", "left": {"ref": "price"}, "right": {"ref": "bb_lower"}},
    {"op": "lt", "left": {"ref": "rsi14"}, "right": {"const": 35}}
  ]},
  "exit": {"op": "crosses_above", "left": {"ref": "price"}, "right": {"ref": "bb_mid"}}
}

- 값 노드: {"const": 숫자} | {"ref": "지표명" | "price" | "volume"}
- 조건 노드: 비교(gt/gte/lt/lte), 교차(crosses_above/crosses_below), 논리(and/or/not)
- 지표 값이 하나라도 None(데이터 부족)이면 조건 전체가 False — 신호 없음 (안전 기본값)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.indicators import (
    calculate_atr,
    calculate_bollinger,
    calculate_ema,
    calculate_highest_high,
    calculate_lowest_low,
    calculate_macd,
    calculate_return_pct,
    calculate_rsi,
    calculate_sma,
    calculate_stochastic_k,
    calculate_volume_ratio,
)


class RuleSpecError(ValueError):
    """DSL 스펙이 유효하지 않을 때."""


# fn 이름 → (계산 함수, 허용 파라미터, 필요 봉수 계산)
def _bollinger_part(index: int):
    def _calc(candles, period=20, num_std=2.0):
        result = calculate_bollinger(candles, int(period), float(num_std))
        return None if result is None else result[index]

    return _calc


_INDICATOR_FNS: dict[str, dict[str, Any]] = {
    "sma": {"calc": lambda c, period=20: calculate_sma(c, int(period)), "params": {"period"}, "bars": lambda p: int(p.get("period", 20)) + 1},
    "ema": {"calc": lambda c, period=20: calculate_ema(c, int(period)), "params": {"period"}, "bars": lambda p: int(p.get("period", 20)) + 1},
    "rsi": {"calc": lambda c, period=14: calculate_rsi(c, int(period)), "params": {"period"}, "bars": lambda p: int(p.get("period", 14)) + 2},
    "atr": {"calc": lambda c, period=14: calculate_atr(c, int(period)), "params": {"period"}, "bars": lambda p: int(p.get("period", 14)) + 2},
    "bollinger_mid": {"calc": _bollinger_part(0), "params": {"period", "num_std"}, "bars": lambda p: int(p.get("period", 20)) + 1},
    "bollinger_upper": {"calc": _bollinger_part(1), "params": {"period", "num_std"}, "bars": lambda p: int(p.get("period", 20)) + 1},
    "bollinger_lower": {"calc": _bollinger_part(2), "params": {"period", "num_std"}, "bars": lambda p: int(p.get("period", 20)) + 1},
    "highest_high": {"calc": lambda c, period=20: calculate_highest_high(c, int(period)), "params": {"period"}, "bars": lambda p: int(p.get("period", 20)) + 2},
    "lowest_low": {"calc": lambda c, period=10: calculate_lowest_low(c, int(period)), "params": {"period"}, "bars": lambda p: int(p.get("period", 10)) + 2},
    "stochastic_k": {"calc": lambda c, period=14: calculate_stochastic_k(c, int(period)), "params": {"period"}, "bars": lambda p: int(p.get("period", 14)) + 1},
    "return_pct": {"calc": lambda c, lookback=5: calculate_return_pct(c, int(lookback)), "params": {"lookback"}, "bars": lambda p: int(p.get("lookback", 5)) + 2},
    "volume_ratio": {"calc": lambda c, period=20: calculate_volume_ratio(c, int(period)), "params": {"period"}, "bars": lambda p: int(p.get("period", 20)) + 1},
    "macd_line": {"calc": lambda c, fast=12, slow=26, signal=9: (lambda r: None if r is None else r.macd)(calculate_macd(c, int(fast), int(slow), int(signal))), "params": {"fast", "slow", "signal"}, "bars": lambda p: int(p.get("slow", 26)) + int(p.get("signal", 9)) + 2},
    "macd_signal": {"calc": lambda c, fast=12, slow=26, signal=9: (lambda r: None if r is None else r.signal)(calculate_macd(c, int(fast), int(slow), int(signal))), "params": {"fast", "slow", "signal"}, "bars": lambda p: int(p.get("slow", 26)) + int(p.get("signal", 9)) + 2},
}

_COMPARE_OPS = {"gt", "gte", "lt", "lte"}
_CROSS_OPS = {"crosses_above", "crosses_below"}
_LOGIC_OPS = {"and", "or", "not"}
_BUILTIN_REFS = {"price", "volume"}
_MAX_DEPTH = 6
_MAX_INDICATORS = 12


def validate_rule_spec(spec: Any) -> None:
    """스펙 구조를 검증한다. 위반 시 RuleSpecError. (임의 코드/미지 연산은 통과 불가)"""
    if not isinstance(spec, dict):
        raise RuleSpecError("rule_spec은 dict여야 합니다")
    if not isinstance(spec.get("name"), str) or not spec["name"].strip():
        raise RuleSpecError("rule_spec.name(문자열)이 필요합니다")
    indicators = spec.get("indicators") or {}
    if not isinstance(indicators, dict) or len(indicators) > _MAX_INDICATORS:
        raise RuleSpecError(f"indicators는 dict(최대 {_MAX_INDICATORS}개)여야 합니다")
    for name, defn in indicators.items():
        if name in _BUILTIN_REFS:
            raise RuleSpecError(f"지표명 {name!r}은 예약어입니다")
        if not isinstance(defn, dict) or defn.get("fn") not in _INDICATOR_FNS:
            raise RuleSpecError(f"지표 {name!r}: 알 수 없는 fn {defn.get('fn')!r}")
        allowed = _INDICATOR_FNS[defn["fn"]]["params"]
        extra = set(defn) - {"fn"} - allowed
        if extra:
            raise RuleSpecError(f"지표 {name!r}: 허용되지 않는 파라미터 {sorted(extra)}")
        for key in set(defn) - {"fn"}:
            value = defn[key]
            if not isinstance(value, (int, float)) or not (0 < float(value) <= 500):
                raise RuleSpecError(f"지표 {name!r}.{key}: 0<값<=500 숫자여야 합니다")
    refs = set(indicators) | _BUILTIN_REFS
    for side in ("entry", "exit"):
        node = spec.get(side)
        if node is None:
            raise RuleSpecError(f"rule_spec.{side} 조건이 필요합니다")
        _validate_condition(node, refs, depth=0, side=side)


def _validate_condition(node: Any, refs: set[str], depth: int, side: str) -> None:
    if depth > _MAX_DEPTH:
        raise RuleSpecError(f"{side}: 조건 중첩이 너무 깊습니다(>{_MAX_DEPTH})")
    if not isinstance(node, dict) or "op" not in node:
        raise RuleSpecError(f"{side}: 조건 노드는 {{'op': ...}} dict여야 합니다")
    op = node["op"]
    if op in _LOGIC_OPS:
        args = node.get("args")
        if op == "not":
            args = args if isinstance(args, list) else [node.get("arg")]
        if not isinstance(args, list) or not args:
            raise RuleSpecError(f"{side}: {op}에는 args 리스트가 필요합니다")
        if op == "not" and len(args) != 1:
            raise RuleSpecError(f"{side}: not은 인자 1개")
        for child in args:
            _validate_condition(child, refs, depth + 1, side)
        return
    if op in _COMPARE_OPS | _CROSS_OPS:
        for key in ("left", "right"):
            _validate_value(node.get(key), refs, side)
        return
    raise RuleSpecError(f"{side}: 알 수 없는 op {op!r}")


def _validate_value(node: Any, refs: set[str], side: str) -> None:
    if not isinstance(node, dict):
        raise RuleSpecError(f"{side}: 값 노드는 dict({{'ref'|'const': ...}})여야 합니다")
    if "const" in node:
        if not isinstance(node["const"], (int, float)):
            raise RuleSpecError(f"{side}: const는 숫자여야 합니다")
        return
    if "ref" in node:
        if node["ref"] not in refs:
            raise RuleSpecError(f"{side}: 정의되지 않은 참조 {node['ref']!r}")
        return
    raise RuleSpecError(f"{side}: 값 노드에 ref 또는 const가 필요합니다")


def required_bars(spec: dict) -> int:
    """스펙 평가에 필요한 최소 봉 수 (+1: 교차 판정용 직전 시점)."""
    needs = [2]
    for defn in (spec.get("indicators") or {}).values():
        fn = _INDICATOR_FNS[defn["fn"]]
        needs.append(fn["bars"]({k: v for k, v in defn.items() if k != "fn"}))
    return max(needs) + 1


class RuleEvaluator:
    """캔들 위에서 스펙의 entry/exit 조건을 평가한다 (현재·직전 시점 지표 계산)."""

    def __init__(self, spec: dict) -> None:
        self._spec = spec

    def _value(self, node: dict, candles: list[MinuteCandle]) -> Decimal | None:
        if "const" in node:
            return Decimal(str(node["const"]))
        ref = node["ref"]
        if ref == "price":
            return candles[-1].close_price
        if ref == "volume":
            return Decimal(candles[-1].volume)
        defn = self._spec["indicators"][ref]
        fn = _INDICATOR_FNS[defn["fn"]]["calc"]
        kwargs = {k: v for k, v in defn.items() if k != "fn"}
        return fn(candles, **kwargs)

    def _eval(self, node: dict, candles: list[MinuteCandle]) -> bool:
        op = node["op"]
        if op == "and":
            return all(self._eval(child, candles) for child in node["args"])
        if op == "or":
            return any(self._eval(child, candles) for child in node["args"])
        if op == "not":
            args = node.get("args") or [node.get("arg")]
            return not self._eval(args[0], candles)
        if op in _CROSS_OPS:
            prev = candles[:-1]
            cur_l, cur_r = self._value(node["left"], candles), self._value(node["right"], candles)
            prev_l, prev_r = self._value(node["left"], prev), self._value(node["right"], prev)
            if None in (cur_l, cur_r, prev_l, prev_r):
                return False
            if op == "crosses_above":
                return prev_l <= prev_r and cur_l > cur_r
            return prev_l >= prev_r and cur_l < cur_r
        left, right = self._value(node["left"], candles), self._value(node["right"], candles)
        if left is None or right is None:
            return False  # 데이터 부족 → 신호 없음 (안전 기본값)
        return {
            "gt": left > right, "gte": left >= right,
            "lt": left < right, "lte": left <= right,
        }[op]

    def entry(self, candles: list[MinuteCandle]) -> bool:
        return self._eval(self._spec["entry"], candles)

    def exit(self, candles: list[MinuteCandle]) -> bool:
        return self._eval(self._spec["exit"], candles)
