from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.news_context import UsMarketSnapshot
from app.domain.repositories.news_context import UsMarketSnapshotRepository

# VIX 구간(레벨). 일반적 통념: ~15 이하 저변동, 25↑ 고변동.
VIX_LOW = 16.0
VIX_HIGH = 25.0
# 지수 평균 변화율(%) 추세 임계.
TREND_THRESHOLD = 0.5
# 반도체(SOX/SOXX) 강약 임계(%).
SEMIS_THRESHOLD = 1.5

REGIME_RISK_ON = "risk_on"
REGIME_NEUTRAL = "neutral"
REGIME_RISK_OFF = "risk_off"
REGIME_UNKNOWN = "unknown"


def _f(v) -> float | None:
    return float(v) if v is not None else None


def classify_macro_regime(snapshot: UsMarketSnapshot | None) -> dict:
    """전일 미국장 스냅샷으로 매크로 레짐을 결정적으로 분류한다 (C-2.49).

    - vix_level: VIX 레벨 구간 (low/elevated/high)
    - us_trend: 나스닥·S&P500 평균 변화율 추세 (up/down/flat)
    - semis_strength: 반도체(SOX/SOXX) 강약 (strong/weak/neutral)
    - regime: risk_on / neutral / risk_off
        risk_off  ← VIX 고변동 또는 미국장 하락 (위험 신호 우선)
        risk_on   ← VIX 저변동 그리고 미국장 상승
        neutral   ← 그 외
    데이터가 없으면 regime="unknown". 이후 제안/스캔 휴리스틱의 입력이 된다.
    """
    if snapshot is None:
        return {
            "regime": REGIME_UNKNOWN, "session_date": None, "vix": None,
            "vix_level": None, "us_trend": None, "us_avg_change_pct": None,
            "semis_strength": None,
        }

    vix = _f(snapshot.vix)
    vix_level = None
    if vix is not None:
        vix_level = "low" if vix < VIX_LOW else "high" if vix > VIX_HIGH else "elevated"

    changes = [
        _f(c) for c in (snapshot.nasdaq_change_pct, snapshot.sp500_change_pct)
        if c is not None
    ]
    us_trend = None
    avg = None
    if changes:
        avg = round(sum(changes) / len(changes), 4)
        us_trend = "up" if avg > TREND_THRESHOLD else "down" if avg < -TREND_THRESHOLD else "flat"

    sox = _f(snapshot.sox_change_pct)
    semis_strength = None
    if sox is not None:
        semis_strength = (
            "strong" if sox > SEMIS_THRESHOLD
            else "weak" if sox < -SEMIS_THRESHOLD else "neutral"
        )

    if vix_level == "high" or us_trend == "down":
        regime = REGIME_RISK_OFF
    elif vix_level == "low" and us_trend == "up":
        regime = REGIME_RISK_ON
    else:
        regime = REGIME_NEUTRAL

    return {
        "regime": regime,
        "session_date": snapshot.session_date.isoformat(),
        "vix": vix,
        "vix_level": vix_level,
        "us_trend": us_trend,
        "us_avg_change_pct": avg,
        "semis_strength": semis_strength,
    }


class MacroRegimeService:
    """최신 미국장 스냅샷에서 매크로 레짐을 산출한다 (C-2.49).

    read-only 분류이며, vision의 "전일 미국장 흐름을 한국장 맥락으로" 잇는 다리다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._us_repo = UsMarketSnapshotRepository(session)

    async def latest_regime(self) -> dict:
        snapshot = await self._us_repo.get_latest()
        return classify_macro_regime(snapshot)

    async def regime_as_of(self, trading_day: date) -> dict:
        """trading_day(KR) 직전에 마감된 미국 세션 기준 레짐.

        KR 거래일은 *전일* 미국장을 보고 움직이므로, trading_day와 같은 날짜의 미국
        세션(아직 끝나지 않은 미래)을 쓰면 룩어헤드가 된다. session_date < trading_day 중
        최신을 골라 이를 막는다. 해당 데이터가 없으면 regime="unknown".
        """
        snapshot = await self._us_repo.get_latest_before(trading_day)
        return classify_macro_regime(snapshot)
