"""스캐너 감시 조건 스키마와 평가 로직 (C-2.23).

조건 정의(검증)와 평가(evaluate)를 순수 로직으로 분리한다. 평가는 종목에 대해
미리 계산된 facts(volume_ratio, turnover_rank, price_change_pct, 수급, 시간대)를 입력받아
조건 충족 여부를 판단한다. 실제 facts를 시장 데이터에서 계산하는 로직은 이후 단계에서 채운다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError, model_validator

from app.domain.models.enums import ScannerConditionType

_VALID_FLOW_VALUES = frozenset({"net_buy", "net_sell"})
_FLOW_KEYS = ("foreign", "institution", "individual")


class InvalidConditionError(ValueError):
    """조건 정의가 유효하지 않을 때 발생."""


class ScannerCondition(BaseModel):
    """단일 감시 조건. type에 따라 params 구조가 다르다."""

    type: ScannerConditionType
    params: dict[str, Any] = {}

    @model_validator(mode="after")
    def _validate_params(self) -> "ScannerCondition":
        p = self.params
        if self.type == ScannerConditionType.VOLUME_SPIKE:
            if not _is_positive_number(p.get("multiplier")):
                raise InvalidConditionError("volume_spike requires positive 'multiplier'")
        elif self.type == ScannerConditionType.TURNOVER_RANK:
            if not _is_positive_int(p.get("max_rank")):
                raise InvalidConditionError("turnover_rank requires positive int 'max_rank'")
        elif self.type == ScannerConditionType.PRICE_CHANGE_PCT:
            if not _is_number(p.get("min_pct")):
                raise InvalidConditionError("price_change_pct requires numeric 'min_pct'")
        elif self.type == ScannerConditionType.INVESTOR_FLOW:
            present = {k: p.get(k) for k in _FLOW_KEYS if p.get(k) is not None}
            if not present:
                raise InvalidConditionError(
                    "investor_flow requires at least one of foreign/institution/individual"
                )
            for k, v in present.items():
                if v not in _VALID_FLOW_VALUES:
                    raise InvalidConditionError(
                        f"investor_flow '{k}' must be one of {sorted(_VALID_FLOW_VALUES)}"
                    )
        elif self.type == ScannerConditionType.TIME_BUCKET:
            buckets = p.get("buckets")
            if not isinstance(buckets, list) or not buckets:
                raise InvalidConditionError("time_bucket requires non-empty 'buckets' list")
        return self


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_positive_number(v: Any) -> bool:
    return _is_number(v) and v > 0


def _is_positive_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def validate_conditions(conditions: list[dict]) -> list[ScannerCondition]:
    """조건 리스트를 검증하고 ScannerCondition 객체 리스트를 반환한다.

    비어 있거나 잘못된 조건이 있으면 InvalidConditionError를 발생시킨다.
    (Pydantic이 검증 에러를 ValidationError로 감싸므로 여기서 InvalidConditionError로 변환한다.)
    """
    if not conditions:
        raise InvalidConditionError("at least one condition is required")
    validated: list[ScannerCondition] = []
    for c in conditions:
        try:
            validated.append(ScannerCondition(**c))
        except ValidationError as e:
            msg = e.errors()[0].get("msg", str(e)) if e.errors() else str(e)
            raise InvalidConditionError(msg) from e
    return validated


@dataclass
class ScannerEvalResult:
    """룰 평가 결과."""

    matched: bool  # 모든 조건 충족 여부 (AND)
    matched_conditions: list[str]  # 충족된 조건 타입 목록
    total: int  # 전체 조건 수
    score: int  # 충족 비율 (0~100)


def _check(condition: dict, facts: dict) -> bool:
    ctype = condition.get("type")
    p = condition.get("params", {})

    if ctype == ScannerConditionType.VOLUME_SPIKE.value:
        vr = facts.get("volume_ratio")
        return vr is not None and vr >= p["multiplier"]
    if ctype == ScannerConditionType.TURNOVER_RANK.value:
        tr = facts.get("turnover_rank")
        return tr is not None and tr <= p["max_rank"]
    if ctype == ScannerConditionType.PRICE_CHANGE_PCT.value:
        pc = facts.get("price_change_pct")
        return pc is not None and pc >= p["min_pct"]
    if ctype == ScannerConditionType.INVESTOR_FLOW.value:
        for k in _FLOW_KEYS:
            if p.get(k) is not None and facts.get(f"{k}_flow") != p[k]:
                return False
        return True
    if ctype == ScannerConditionType.TIME_BUCKET.value:
        return facts.get("time_bucket") in p.get("buckets", [])
    return False


def evaluate_conditions(conditions: list[dict], facts: dict) -> ScannerEvalResult:
    """조건 리스트를 facts에 대해 평가한다 (AND 시맨틱).

    facts 예: {"volume_ratio": 2.1, "turnover_rank": 23, "price_change_pct": 4.8,
              "foreign_flow": "net_buy", "time_bucket": "morning"}
    """
    total = len(conditions)
    matched_types = [c["type"] for c in conditions if _check(c, facts)]
    matched = total > 0 and len(matched_types) == total
    score = round(len(matched_types) / total * 100) if total else 0
    return ScannerEvalResult(
        matched=matched,
        matched_conditions=matched_types,
        total=total,
        score=score,
    )
