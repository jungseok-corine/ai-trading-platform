"""LLM 분석 출력(JSON) 파서 (C-2.56).

일일 분석가에게 구조화 JSON으로 답하라고 지시하고(JSON_OUTPUT_INSTRUCTION), 응답 텍스트에서
JSON 블록을 관대하게 추출·검증한다. 모델이 코드펜스/잡설을 섞어도 첫 균형 JSON 객체를 찾는다.
순수 함수 — 네트워크/DB 없음.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

# 프롬프트 말미에 덧붙이는 출력 형식 지시. 분석가가 이 스키마로 답하게 한다.
JSON_OUTPUT_INSTRUCTION = (
    "반드시 아래 JSON 객체 '하나만' 출력하라(설명/코드펜스 없이):\n"
    "{\n"
    '  "verdict": "improve | keep | investigate",\n'
    '  "key_observations": ["데이터 근거 관찰 1~3개"],\n'
    '  "mistakes": ["이 매매/전략의 구체적 실수"],\n'
    '  "hypotheses": [\n'
    '    {"hypothesis": "...", "param_change": {"long_window": 25},\n'
    '     "confidence": 0.0, "rationale": "왜 이 변경이 도움되는가"}\n'
    "  ],\n"
    '  "risk_notes": "...",\n'
    '  "confidence": 0.0\n'
    "}\n"
    "param_change는 실제 전략 파라미터 키만 사용하라(없으면 빈 객체). 근거가 약하면 confidence를 낮춰라."
)


def _to_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _extract_json_object(text: str) -> dict | None:
    """텍스트에서 첫 균형 잡힌 JSON 객체를 추출한다(코드펜스/잡설 허용)."""
    if not text:
        return None
    # 1) 통째로 시도
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, TypeError):
        pass
    # 2) 첫 '{'부터 중괄호 균형으로 잘라 시도
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        break  # 이 start는 실패 → 다음 '{'로
        start = text.find("{", start + 1)
    return None


@dataclass
class Hypothesis:
    hypothesis: str
    param_change: dict
    confidence: float | None
    rationale: str | None


@dataclass
class AnalysisOutput:
    verdict: str | None
    confidence: float | None
    key_observations: list = field(default_factory=list)
    mistakes: list = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    risk_notes: str | None = None
    raw: dict = field(default_factory=dict)

    def best_hypothesis(self, min_confidence: float) -> Hypothesis | None:
        """param_change가 있고 confidence가 임계 이상인 가설 중 최고 confidence 1개."""
        best: Hypothesis | None = None
        for h in self.hypotheses:
            if not h.param_change:
                continue
            conf = h.confidence if h.confidence is not None else (self.confidence or 0.0)
            if conf >= min_confidence and (best is None or conf > (best.confidence or 0.0)):
                best = h
        return best


def parse_analysis_output(text: str) -> AnalysisOutput | None:
    """응답 텍스트에서 분석 JSON을 파싱한다. JSON을 못 찾으면 None."""
    obj = _extract_json_object(text)
    if obj is None:
        return None
    hyps: list[Hypothesis] = []
    for h in obj.get("hypotheses") or []:
        if not isinstance(h, dict):
            continue
        pc = h.get("param_change")
        hyps.append(Hypothesis(
            hypothesis=str(h.get("hypothesis", "")),
            param_change=pc if isinstance(pc, dict) else {},
            confidence=_to_float(h.get("confidence")),
            rationale=h.get("rationale"),
        ))
    return AnalysisOutput(
        verdict=obj.get("verdict"),
        confidence=_to_float(obj.get("confidence")),
        key_observations=obj.get("key_observations") or [],
        mistakes=obj.get("mistakes") or [],
        hypotheses=hyps,
        risk_notes=obj.get("risk_notes"),
        raw=obj,
    )
