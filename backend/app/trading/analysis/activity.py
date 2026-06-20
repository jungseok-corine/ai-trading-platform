"""활동량 진단 게이트 — '신호가 적/많/없음'을 시장 활발도와 함께 판정한다 (C-2.54).

신호가 없다는 것 자체가 신호다(조건이 너무 빡셀 수 있음). 그래서 단순 skip이 아니라:
  - 무신호 + 시장도 죽음 → skip (진짜 배울 게 없음)
  - 적음/무신호 + 시장은 활발 → 분석(왜 안 잡았나? 조건 과빡 의심) ← 가장 가치있는 케이스
  - 적정 → 일반 성과 분석
  - 과다 → 과매매/조건 느슨 의심
순수 함수 — DB/네트워크 없음.
"""
from __future__ import annotations

from dataclasses import dataclass

BAND_NONE_QUIET = "none_quiet"
BAND_SPARSE = "sparse"
BAND_NORMAL = "normal"
BAND_EXCESSIVE = "excessive"


@dataclass
class ActivityAssessment:
    band: str
    should_analyze: bool
    market_active: bool
    signal_count: int
    reason: str

    def to_dict(self) -> dict:
        return {
            "band": self.band,
            "should_analyze": self.should_analyze,
            "market_active": self.market_active,
            "signal_count": self.signal_count,
            "reason": self.reason,
        }


def assess_activity(
    signal_count: int,
    range_pct: float | None,
    notable_count: int,
    *,
    few_threshold: int = 3,
    many_threshold: int = 15,
    active_range_pct: float = 2.0,
    active_notable: int = 3,
) -> ActivityAssessment:
    """그날 신호 수 + 시장 활발도로 분석 여부와 진단 밴드를 정한다.

    market_active: 당일 레인지가 active_range_pct% 이상이거나 notable 사건이 active_notable
    이상이면 '시장 활발'로 본다.
    """
    market_active = (range_pct or 0.0) >= active_range_pct or notable_count >= active_notable

    if signal_count == 0 and not market_active:
        return ActivityAssessment(
            band=BAND_NONE_QUIET, should_analyze=False, market_active=False,
            signal_count=signal_count,
            reason="무신호 + 시장 비활발 → 분석 생략(배울 데이터 없음).",
        )

    if signal_count < few_threshold:
        note = "조건이 과도하게 빡셀 가능성(시장은 활발한데 미발화)." if market_active else "시장도 조용했음."
        return ActivityAssessment(
            band=BAND_SPARSE, should_analyze=True, market_active=market_active,
            signal_count=signal_count,
            reason=f"신호 적음({signal_count}건). {note}",
        )

    if signal_count > many_threshold:
        return ActivityAssessment(
            band=BAND_EXCESSIVE, should_analyze=True, market_active=market_active,
            signal_count=signal_count,
            reason=f"신호 과다({signal_count}건) → 과매매/조건 과완화 의심.",
        )

    return ActivityAssessment(
        band=BAND_NORMAL, should_analyze=True, market_active=market_active,
        signal_count=signal_count, reason=f"정상 활동({signal_count}건).",
    )
