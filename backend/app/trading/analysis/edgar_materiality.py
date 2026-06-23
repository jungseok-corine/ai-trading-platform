"""SEC EDGAR 공시 유형(form type) 중요도 점수 — 룰 기반 (C-5.20).

미국 공시는 form type이 분명해 유형만으로 중요도를 잘 가늠할 수 있다(KR DART와 동형).
"주가에 영향 없는 공시는 AI가 볼 필요 없다"는 요구를 form type으로 1차 필터한다.
순수 함수 — 네트워크/DB 없음.
"""
from __future__ import annotations

CATEGORY_HIGH = "high"
CATEGORY_MEDIUM = "medium"
CATEGORY_LOW = "low"
CATEGORY_NOISE = "noise"

# 고중요(주가 직접 영향): 수시공시·정기보고서·외국기업 보고서
_HIGH_PREFIXES = ("8-K", "10-K", "10-Q", "6-K", "20-F", "40-F")
# 중간(잠재 영향): 지분변동·증권발행·등록신고
_MEDIUM_PREFIXES = (
    "SC 13D", "SC 13G", "SC TO", "424B", "S-1", "S-3", "F-1", "F-3", "425",
    "DEFM14A", "DEF 14A", "PREM14A", "8-A",
)
# 저중요(내부자 거래 등): 보통 단건 영향은 작지만 누적 신호.
_LOW_PREFIXES = ("4", "3", "5", "144")


def _base(form: str) -> str:
    # form 끝의 "/A"(정정)는 같은 유형으로 본다(예: "8-K/A" → "8-K").
    return form.split("/")[0].strip()


def _matches_prefix(form: str, prefixes: tuple[str, ...]) -> bool:
    base = _base(form)
    return any(base == p or base.startswith(p) for p in prefixes)


def score_form_materiality(form: str) -> tuple[float, str]:
    """form type 중요도를 (score 0~1, category)로 반환한다."""
    f = (form or "").strip().upper()
    if _matches_prefix(f, tuple(p.upper() for p in _HIGH_PREFIXES)):
        return 0.9, CATEGORY_HIGH
    if _matches_prefix(f, tuple(p.upper() for p in _MEDIUM_PREFIXES)):
        return 0.6, CATEGORY_MEDIUM
    # 내부자 보고(3/4/5/144)는 정확히 일치할 때만(접두 매칭은 과대매칭).
    if _base(f) in {p.upper() for p in _LOW_PREFIXES}:
        return 0.3, CATEGORY_LOW
    return 0.15, CATEGORY_NOISE
