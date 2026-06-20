"""매크로 레짐을 후보 점수에 반영 (C-2.63).

전일 미국장 매크로(C-2.49)를 스캔 단계 후보 점수에 결정적으로 반영한다.
- risk_off(위험회피): 신규 후보 점수를 낮춰(보수적) 진입을 자제.
- risk_on: 소폭 가산.
- SOX(반도체) 강세 + 반도체 테마 종목: 가산 / SOX 약세: 감산.
순수 함수 — DB/네트워크 없음.
"""
from __future__ import annotations

RISK_OFF_FACTOR = 0.85
RISK_ON_FACTOR = 1.05
SEMIS_STRONG_FACTOR = 1.15
SEMIS_WEAK_FACTOR = 0.9


def macro_score_adjustment(
    score: int,
    regime: str | None,
    semis_strength: str | None,
    is_semis: bool,
) -> int:
    """후보 점수(0~100)를 매크로 레짐으로 조정한다."""
    factor = 1.0
    if regime == "risk_off":
        factor *= RISK_OFF_FACTOR
    elif regime == "risk_on":
        factor *= RISK_ON_FACTOR
    if is_semis:
        if semis_strength == "strong":
            factor *= SEMIS_STRONG_FACTOR
        elif semis_strength == "weak":
            factor *= SEMIS_WEAK_FACTOR
    return int(round(min(100.0, max(0.0, score * factor))))
