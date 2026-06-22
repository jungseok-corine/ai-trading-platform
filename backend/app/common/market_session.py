"""시장 세션(장 운영시간) 판단 — KR(KRX)/US 정규장 등.

KIS는 "장이 열렸다/닫혔다"를 직접 알려주지 않으므로 서버에서 시각 기준으로 판단한다.
이 모듈은 순수 함수만 제공한다(외부 의존 없음, now를 인자로 받아 테스트 용이).

한계:
    - 공휴일(임시휴장 포함)은 시각만으로 알 수 없다 → 별도 캘린더 없이는 평일로 간주된다.
      실제 휴장일에는 시세가 갱신되지 않으므로 캔들 신선도 가드(SignalService)가 백스톱으로
      허위 신호를 막는다. 세션 게이트는 "주말/장외 시간"의 명백한 케이스를 싸게 걸러낸다.
    - NXT(넥스트레이드)/US 확장시간(프리/애프터)은 KIS 모의투자 주문 미지원이라 Phase A에선
      세션 단계만 노출하고 주문 라우팅은 추후(실거래) 단계에서 얹는다.
"""
from __future__ import annotations

from datetime import datetime, time
from enum import Enum
from zoneinfo import ZoneInfo

from app.common.timezone import KST

# 미국 동부시간(서머타임 자동 처리).
ET = ZoneInfo("America/New_York")


class MarketPhase(str, Enum):
    """시장 운영 단계."""

    CLOSED = "closed"                       # 휴장(주말/장외 시간)
    PRE = "pre"                             # 장전 동시호가/프리마켓
    REGULAR = "regular"                     # 정규 연속매매
    CLOSING_AUCTION = "closing_auction"     # 종가 동시호가(KR 15:20~15:30)
    POST = "post"                           # 장후 시간외/애프터마켓


# 연속 시세가 흐르며 신호 생성이 의미 있는 단계.
_SIGNAL_ACTIVE_PHASES = frozenset({MarketPhase.REGULAR, MarketPhase.CLOSING_AUCTION})


def kr_market_phase(now: datetime) -> MarketPhase:
    """KRX(한국거래소) 정규장 기준 현재 시장 단계를 반환한다(KST).

    - 08:30~09:00  장전 동시호가(PRE)
    - 09:00~15:20  정규 연속매매(REGULAR)
    - 15:20~15:30  종가 동시호가(CLOSING_AUCTION)
    - 15:30~18:00  장후/시간외단일가(POST)
    - 그 외/주말    휴장(CLOSED)
    """
    now = now.astimezone(KST)
    if now.weekday() >= 5:  # 5=토, 6=일
        return MarketPhase.CLOSED
    t = now.time()
    if time(8, 30) <= t < time(9, 0):
        return MarketPhase.PRE
    if time(9, 0) <= t < time(15, 20):
        return MarketPhase.REGULAR
    if time(15, 20) <= t < time(15, 30):
        return MarketPhase.CLOSING_AUCTION
    if time(15, 30) <= t < time(18, 0):
        return MarketPhase.POST
    return MarketPhase.CLOSED


def us_market_phase(now: datetime) -> MarketPhase:
    """미국 시장 기준 현재 단계를 반환한다(미 동부시간 ET, 서머타임 자동).

    - 04:00~09:30 ET  프리마켓(PRE)
    - 09:30~16:00 ET  정규장(REGULAR)
    - 16:00~20:00 ET  애프터마켓(POST)
    - 그 외/주말       휴장(CLOSED)
    """
    et = now.astimezone(ET)
    if et.weekday() >= 5:
        return MarketPhase.CLOSED
    t = et.time()
    if time(4, 0) <= t < time(9, 30):
        return MarketPhase.PRE
    if time(9, 30) <= t < time(16, 0):
        return MarketPhase.REGULAR
    if time(16, 0) <= t < time(20, 0):
        return MarketPhase.POST
    return MarketPhase.CLOSED


def market_phase(market: str, now: datetime) -> MarketPhase:
    """시장 코드(KR/US)에 맞는 시장 단계를 반환한다."""
    if market == "US":
        return us_market_phase(now)
    return kr_market_phase(now)


def is_signal_active(market: str, now: datetime) -> bool:
    """해당 시장에서 지금 신호 생성이 의미 있는 단계(정규/종가동시호가)인지 여부."""
    return market_phase(market, now) in _SIGNAL_ACTIVE_PHASES


def is_closing_auction(market: str, now: datetime) -> bool:
    """해당 시장이 종가 동시호가 단계인지 여부(종가 매도 결정 시점)."""
    return market_phase(market, now) == MarketPhase.CLOSING_AUCTION
