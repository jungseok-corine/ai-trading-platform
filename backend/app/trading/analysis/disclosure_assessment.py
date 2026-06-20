"""공시 영향 평가 — 온디맨드 LLM 평가 (C-2.62).

수집된 공시(C-2.59)가 보유/관심 종목에 어떤 영향인지 사람이 요청할 때 LLM에게 묻는다.
출력은 구조화 JSON. AI는 평가만 — 자동매매/주문 없음(감지·표시·평가, 대응은 사람).
순수 프롬프트 빌더 + 파서를 분리해 테스트한다.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.trading.analysis.analysis_output import _extract_json_object, _to_float

DISCLOSURE_PROMPT_INSTRUCTION = (
    "너는 한국 주식 트레이딩 보조 분석가다. 아래 공시가 '보유 포지션'에 미칠 단기 영향을 평가하라.\n"
    "반드시 아래 JSON 객체 하나만 출력하라(설명/코드펜스 없이):\n"
    "{\n"
    '  "impact": "positive | negative | neutral",\n'
    '  "severity": 0.0,                          // 0(미미)~1(매우 큼)\n'
    '  "action_hint": "hold | watch | reduce | exit | none",\n'
    '  "rationale": "한 줄 근거",\n'
    '  "confidence": 0.0\n'
    "}\n"
    "공시 유형이 모호하거나 영향이 불확실하면 impact=neutral, action_hint=watch로 두고 confidence를 낮춰라."
)


def build_disclosure_prompt(
    symbol_code: str,
    headline: str,
    category: str | None,
    corp_name: str | None,
    holding_note: str | None = None,
) -> str:
    lines = [
        "[공시 영향 평가 요청]",
        f"종목: {symbol_code} ({corp_name or '-'})",
        f"공시: {headline}",
        f"공시 중요도 분류(룰): {category or '미상'}",
    ]
    if holding_note:
        lines.append(f"보유 맥락: {holding_note}")
    lines.append("")
    lines.append(DISCLOSURE_PROMPT_INSTRUCTION)
    return "\n".join(lines)


@dataclass
class DisclosureAssessment:
    impact: str | None
    severity: float | None
    action_hint: str | None
    rationale: str | None
    confidence: float | None

    def to_dict(self) -> dict:
        return {
            "impact": self.impact, "severity": self.severity,
            "action_hint": self.action_hint, "rationale": self.rationale,
            "confidence": self.confidence,
        }


_VALID_IMPACT = {"positive", "negative", "neutral"}
_VALID_ACTION = {"hold", "watch", "reduce", "exit", "none"}


def parse_disclosure_assessment(text: str) -> DisclosureAssessment | None:
    """LLM 응답에서 평가 JSON을 파싱한다. 못 찾으면 None. 잘못된 enum은 보정한다."""
    obj = _extract_json_object(text)
    if obj is None:
        return None
    impact = obj.get("impact")
    if impact not in _VALID_IMPACT:
        impact = "neutral"
    action = obj.get("action_hint")
    if action not in _VALID_ACTION:
        action = "watch"
    return DisclosureAssessment(
        impact=impact,
        severity=_to_float(obj.get("severity")),
        action_hint=action,
        rationale=obj.get("rationale"),
        confidence=_to_float(obj.get("confidence")),
    )
