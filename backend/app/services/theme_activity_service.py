"""테마 활동 감지 및 시너지 점수 계산 (C-2.23).

ThemeActivityService: 최근 IntelligenceEvent 기반 활성 테마 탐지.
compute_theme_synergy_bonus: symbol_themes ∩ active_themes 교집합 수 × bonus_per_theme.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import MarketCode
from app.domain.repositories.intelligence import IntelligenceEventRepository
from app.domain.repositories.market_context import ThemeRepository


class ThemeActivityService:
    """최근 IntelligenceEvent에서 활성 테마를 탐지한다.

    Theme.code / Theme.name이 이벤트 title+summary 텍스트에 등장하는지
    단순 문자열 포함 여부로 판단한다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._event_repo = IntelligenceEventRepository(session)
        self._theme_repo = ThemeRepository(session)

    async def get_active_themes(
        self,
        market: MarketCode,
        lookback_hours: int = 24,
        event_limit: int = 100,
    ) -> dict:
        """최근 N시간 이벤트에서 테마 키워드가 등장한 테마 목록을 반환한다.

        Returns:
            {
                "active_themes": list[str],   # Theme.code 목록
                "hot_count": int,
                "matched_events": int,
                "lookback_hours": int,
            }
        """
        events = await self._event_repo.list_recent(
            hours=lookback_hours, market=market, limit=event_limit
        )
        themes = await self._theme_repo.list_by_market(market)

        active_theme_codes: list[str] = []
        total_matched_events = 0

        for theme in themes:
            keywords = {theme.code.lower(), theme.name.lower()}
            theme_matched = False
            for event in events:
                text = (
                    (event.title or "").lower()
                    + " "
                    + (event.summary or "").lower()
                )
                if any(kw in text for kw in keywords):
                    if not theme_matched:
                        active_theme_codes.append(theme.code)
                        theme_matched = True
                    total_matched_events += 1

        return {
            "active_themes": active_theme_codes,
            "hot_count": len(active_theme_codes),
            "matched_events": total_matched_events,
            "lookback_hours": lookback_hours,
        }


def compute_theme_synergy_bonus(
    symbol_themes: list[str],
    active_themes: list[str],
    bonus_per_theme: int = 10,
) -> int:
    """symbol_themes와 active_themes의 교집합 테마 수 × bonus_per_theme를 반환한다.

    CandidateEvent.score를 직접 수정하지 않는다 — 호출자가 사용 여부를 결정한다.
    """
    return len(set(symbol_themes) & set(active_themes)) * bonus_per_theme
