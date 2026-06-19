"""종목 facts 계산 (C-2.31).

스캐너 룰이 평가하는 facts(volume_ratio / price_change_pct / turnover_rank / 수급 / 시간대)를
시장 데이터·수급 데이터로부터 계산하는 순수 함수 모음. 데이터 소스(KIS/DB)와 분리되어 있어
입력만 주면 단위 테스트가 가능하다.
"""
from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def time_bucket(dt: datetime) -> str:
    """KST 기준 시간대 버킷. (한국장 기준)"""
    t = dt.astimezone(KST).time()
    if t < time(9, 0):
        return "premarket"
    if t < time(11, 0):
        return "morning"
    if t < time(13, 0):
        return "midday"
    if t <= time(15, 30):
        return "afternoon"
    return "after_hours"


def flow_direction(net_quantity: int | None) -> str | None:
    """순매수 수량 → net_buy / net_sell / neutral (None이면 None)."""
    if net_quantity is None:
        return None
    if net_quantity > 0:
        return "net_buy"
    if net_quantity < 0:
        return "net_sell"
    return "neutral"


def compute_volume_ratio(volumes: list[int], period: int) -> Decimal | None:
    """현재 거래량 / 최근 period개 거래량 평균. 데이터 부족/0이면 None.

    indicators.calculate_volume_ratio와 동일한 정의(현재 거래량 포함 평균)이다.
    """
    if period <= 0 or len(volumes) < period:
        return None
    window = [Decimal(v) for v in volumes[-period:]]
    vsma = sum(window, Decimal(0)) / period
    if vsma == 0:
        return None
    return Decimal(volumes[-1]) / vsma


def compute_price_change_pct(
    closes: list[Decimal], reference_price: Decimal | None = None
) -> Decimal | None:
    """기준가 대비 최신 종가의 변화율(%). 기준가 미지정 시 첫 종가를 사용한다."""
    if not closes:
        return None
    base = reference_price if reference_price is not None else closes[0]
    if base == 0:
        return None
    return (closes[-1] - base) / base * 100


def compute_symbol_facts(
    closes: list[Decimal],
    volumes: list[int],
    *,
    latest_flow=None,
    now: datetime,
    volume_window: int = 20,
    reference_price: Decimal | None = None,
) -> dict:
    """단일 종목의 facts를 계산한다(turnover_rank 제외 — 종목 간 비교가 필요하므로 별도).

    latest_flow: InvestorFlow 객체(또는 None). foreign/institution/individual 순매수 수량을 읽는다.
    """
    facts: dict = {
        "volume_ratio": _to_float(compute_volume_ratio(volumes, volume_window)),
        "price_change_pct": _to_float(compute_price_change_pct(closes, reference_price)),
        "current_volume": volumes[-1] if volumes else None,
        "time_bucket": time_bucket(now),
    }
    if latest_flow is not None:
        facts["foreign_flow"] = flow_direction(latest_flow.foreign_net_buy_quantity)
        facts["institution_flow"] = flow_direction(latest_flow.institution_net_buy_quantity)
        facts["individual_flow"] = flow_direction(latest_flow.individual_net_buy_quantity)
    return facts


def assign_turnover_ranks(
    facts_by_symbol: dict[str, dict], turnover_by_symbol: dict[str, Decimal]
) -> None:
    """종목별 거래대금(turnover)으로 순위를 매겨 각 facts에 turnover_rank를 추가한다(in-place).

    rank 1 = 거래대금 최상위. turnover가 없는 종목은 rank를 매기지 않는다.
    """
    ranked = sorted(
        (s for s in turnover_by_symbol if turnover_by_symbol[s] is not None),
        key=lambda s: turnover_by_symbol[s],
        reverse=True,
    )
    for idx, symbol in enumerate(ranked, start=1):
        if symbol in facts_by_symbol:
            facts_by_symbol[symbol]["turnover_rank"] = idx


def _to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None
