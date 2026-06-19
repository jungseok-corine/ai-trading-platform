from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import MarketCode
from app.domain.models.market_context import MarketContextSnapshot, Theme
from app.domain.models.signal_log import SignalLog
from app.domain.models.trade import Trade
from app.domain.repositories.market_context import (
    MarketContextSnapshotRepository,
    SymbolThemeMembershipRepository,
    ThemeRepository,
)


class MarketContextService:
    """시장/테마 맥락(context) 데이터를 생성·조회하고 signal/trade에 연결한다.

    C-2.22 Foundation: 데이터 구조와 연결 배관을 제공한다. 실제 시장 데이터를
    자동 수집·태깅하는 로직(뉴스/테마 감지 등)은 이후 단계에서 채운다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._snapshot_repo = MarketContextSnapshotRepository(session)
        self._theme_repo = ThemeRepository(session)
        self._membership_repo = SymbolThemeMembershipRepository(session)

    # --- snapshot --------------------------------------------------------
    async def create_snapshot(
        self, market: MarketCode = MarketCode.KR, **fields
    ) -> MarketContextSnapshot:
        """시장 맥락 스냅샷을 생성한다.

        fields로 time_bucket, index_trend, foreign_flow, institution_flow,
        individual_flow, news_sentiment, indices, us_previous_session, fx, data 등을
        전달할 수 있다.
        """
        snapshot = await self._snapshot_repo.create(market=market, **fields)
        await self._session.commit()
        return snapshot

    async def get_snapshot(self, snapshot_id: int) -> MarketContextSnapshot | None:
        return await self._snapshot_repo.get(snapshot_id)

    async def list_snapshots(
        self, market: MarketCode | None = None, limit: int = 50
    ) -> list[MarketContextSnapshot]:
        return await self._snapshot_repo.list_recent(market=market, limit=limit)

    async def attach_snapshot_to_signal(self, signal_id: int, snapshot_id: int) -> bool:
        """signal_log에 context_snapshot_id를 연결한다. 대상이 없으면 False."""
        signal = await self._session.get(SignalLog, signal_id)
        snapshot = await self._snapshot_repo.get(snapshot_id)
        if signal is None or snapshot is None:
            return False
        signal.context_snapshot_id = snapshot_id
        await self._session.commit()
        return True

    async def attach_snapshot_to_trade(self, trade_id: int, snapshot_id: int) -> bool:
        """trade에 context_snapshot_id를 연결한다. 대상이 없으면 False."""
        trade = await self._session.get(Trade, trade_id)
        snapshot = await self._snapshot_repo.get(snapshot_id)
        if trade is None or snapshot is None:
            return False
        trade.context_snapshot_id = snapshot_id
        await self._session.commit()
        return True

    # --- themes ----------------------------------------------------------
    async def upsert_theme(self, market: MarketCode, code: str, name: str) -> Theme:
        """테마를 생성하거나 기존 테마를 반환한다 (market+code 기준 멱등)."""
        existing = await self._theme_repo.get_by_code(market, code)
        if existing is not None:
            return existing
        theme = await self._theme_repo.create(market, code, name)
        await self._session.commit()
        return theme

    async def list_themes(self, market: MarketCode | None = None) -> list[Theme]:
        return await self._theme_repo.list_by_market(market)

    async def tag_symbol(self, symbol_code: str, theme_id: int, market: MarketCode) -> bool:
        """종목을 테마에 매핑한다. 이미 매핑돼 있으면 False(중복 생성 안 함), 신규면 True."""
        if await self._membership_repo.exists(symbol_code, theme_id):
            return False
        await self._membership_repo.create(market, symbol_code, theme_id)
        await self._session.commit()
        return True

    async def list_themes_for_symbol(self, symbol_code: str) -> list[Theme]:
        return await self._membership_repo.list_themes_for_symbol(symbol_code)
