"""뉴스 중요도 LLM 정밀 점수 (C-2.65).

룰 기반 점수(C-2.57)는 키워드가 분명한 공시엔 강하지만, 비정형 뉴스에서 중요한 걸 놓칠 수
있다. 싼 모델(큐레이터 티어)로 헤드라인별 materiality(0~1)를 보강한다. 순수 프롬프트/파서.
"""
from __future__ import annotations

from app.trading.analysis.analysis_output import _extract_json_object, _to_float

NEWS_SCORING_INSTRUCTION = (
    "아래 뉴스 헤드라인들이 해당 종목 주가에 미칠 '중요도'를 각각 0.0~1.0으로 매겨라.\n"
    "주가에 큰 영향(실적·계약·자본구조·사건사고)=높게, 홍보·일정·정정=낮게.\n"
    "반드시 JSON 배열 하나만 출력하라(설명 없이): "
    '[{"i": 0, "score": 0.0}, {"i": 1, "score": 0.0}, ...]'
)


def build_news_scoring_prompt(headlines: list[str]) -> str:
    lines = ["[뉴스 중요도 평가]"]
    for i, h in enumerate(headlines):
        lines.append(f"{i}. {h}")
    lines.append("")
    lines.append(NEWS_SCORING_INSTRUCTION)
    return "\n".join(lines)


def parse_news_scores(text: str, n: int) -> list[float | None]:
    """응답에서 길이 n의 점수 리스트를 파싱한다. 못 찾으면 전부 None.

    JSON 배열 [{i, score}] 또는 객체에 감싼 배열을 관대하게 처리한다.
    """
    scores: list[float | None] = [None] * n
    arr = _extract_json_array(text)
    if arr is None:
        return scores
    for item in arr:
        if not isinstance(item, dict):
            continue
        idx = item.get("i")
        if isinstance(idx, int) and 0 <= idx < n:
            s = _to_float(item.get("score"))
            if s is not None:
                scores[idx] = max(0.0, min(1.0, s))
    return scores


def _extract_json_array(text: str) -> list | None:
    import json

    if not text:
        return None
    start = text.find("[")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                        if isinstance(obj, list):
                            return obj
                    except json.JSONDecodeError:
                        break
        start = text.find("[", start + 1)
    # 객체 안에 배열이 있는 경우
    obj = _extract_json_object(text)
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, list):
                return v
    return None
