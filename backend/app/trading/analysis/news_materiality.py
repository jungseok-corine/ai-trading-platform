"""뉴스/공시 중요도(materiality) 점수 — 룰 기반 (C-2.57).

"주가에 영향 없는 뉴스는 AI가 볼 필요 없다"는 요구를 룰로 1차 필터한다. KR 공시/뉴스
헤드라인의 키워드로 중요도를 0~1로 매기고 분류한다. DART 공시처럼 유형이 분명한 경우
정확도가 높다. (비정형 뉴스의 정밀 점수는 이후 싼 모델 큐레이터로 보강 — C-2.57+.)
순수 함수 — 네트워크/DB 없음.
"""
from __future__ import annotations

# 고중요(주가 직접 영향): 실적·공급계약·자본구조·지배구조·악재성 사건
_HIGH = (
    "잠정실적", "영업이익", "실적", "공급계약", "단일판매", "수주", "납품계약",
    "유상증자", "무상증자", "전환사채", "신주인수권", "유상감자", "무상감자",
    "합병", "분할", "영업양수도", "자기주식", "자사주", "최대주주", "경영권",
    "횡령", "배임", "거래정지", "상장폐지", "관리종목", "영업정지", "리콜",
    "특별관계자", "공개매수", "배당",
)
# 중간(잠재 영향): 신제품·기술·협약·투자 등
_MEDIUM = (
    "신제품", "특허", "임상", "승인", "협약", "MOU", "투자유치", "목표주가",
    "수출", "계약", "출시", "증설", "양산",
)
# 노이즈(보통 무영향): 정정·일정·홍보성
_NOISE = (
    "정정", "기재정정", "첨부정정", "IR", "기업설명회", "컨퍼런스", "일정",
    "안내", "수상", "후원", "ESG보고서",
)

CATEGORY_HIGH = "high"
CATEGORY_MEDIUM = "medium"
CATEGORY_LOW = "low"
CATEGORY_NOISE = "noise"


def score_materiality(headline: str, themes: list | None = None) -> tuple[float, str]:
    """헤드라인 중요도를 (score 0~1, category)로 반환한다.

    고중요 키워드가 있으면 noise 키워드가 섞여도 고중요로 본다(중요 공시의 정정 등).
    """
    h = headline or ""
    if any(k in h for k in _HIGH):
        return 0.9, CATEGORY_HIGH
    if any(k in h for k in _MEDIUM):
        return 0.6, CATEGORY_MEDIUM
    if any(k in h for k in _NOISE):
        return 0.15, CATEGORY_NOISE
    # 테마가 달려 있으면 약간 가산(종목/테마 연관 뉴스).
    return (0.4, CATEGORY_LOW) if themes else (0.3, CATEGORY_LOW)


def is_material(headline: str, themes: list | None = None, min_score: float = 0.5) -> bool:
    score, _ = score_materiality(headline, themes)
    return score >= min_score
