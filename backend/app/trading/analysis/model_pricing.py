"""AI 모델 토큰 단가표 + 비용 추정 (C-3.1).

순수 함수. 외부 호출 없음. 단가는 **추정치**(USD / 100만 토큰, input/output 분리)이며
공급사 가격이 바뀌면 여기만 갱신한다. 표에 없는 모델은 unpriced로 표시하고 비용 0으로 둔다
(비용을 0으로 과소계상하기보다 "가격 미상"임을 운영자에게 드러내는 게 안전).

비용 가드 철학: 우리는 토큰 사용량을 항상 기록하므로, 단가가 부정확해도 사용량 자체로
이상 급증을 감지할 수 있다. 단가표는 어디까지나 "대략 얼마"의 가늠자.
"""
from __future__ import annotations

# (input_usd_per_1m, output_usd_per_1m). 키는 소문자 모델 식별자(부분일치 허용).
# 추정치 — 운영 시점에 공급사 공식 단가로 재확인할 것.
_PRICE_TABLE: dict[str, tuple[float, float]] = {
    # OpenAI 세대
    "gpt-5.5": (5.0, 15.0),
    "gpt-5.4-mini": (0.15, 0.60),
    "gpt-5.4": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.5, 10.0),
    # Anthropic 세대
    "claude-opus": (15.0, 75.0),
    "claude-sonnet": (3.0, 15.0),
    "claude-haiku": (1.0, 5.0),
    # 테스트용(무료)
    "fake": (0.0, 0.0),
}

_PER_MILLION = 1_000_000.0


def lookup_price(model: str | None) -> tuple[float, float] | None:
    """모델 식별자로 (input, output) 단가를 찾는다. 못 찾으면 None.

    정확 일치 우선, 없으면 가장 긴 부분일치 키를 쓴다(예: 'gpt-5.4-mini'가
    'gpt-5.4'보다 우선되도록).
    """
    if not model:
        return None
    name = model.strip().lower()
    if name in _PRICE_TABLE:
        return _PRICE_TABLE[name]
    best: tuple[str, tuple[float, float]] | None = None
    for key, price in _PRICE_TABLE.items():
        if key in name and (best is None or len(key) > len(best[0])):
            best = (key, price)
    return best[1] if best else None


def estimate_cost(
    model: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> tuple[float, bool]:
    """(USD 비용, priced 여부)를 반환한다. 단가 미상이면 (0.0, False).

    토큰이 None이면 0으로 본다.
    """
    price = lookup_price(model)
    if price is None:
        return 0.0, False
    in_rate, out_rate = price
    cost = (prompt_tokens or 0) / _PER_MILLION * in_rate
    cost += (completion_tokens or 0) / _PER_MILLION * out_rate
    return round(cost, 6), True
