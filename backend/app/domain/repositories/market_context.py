from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import MarketCode
from app.domain.models.market_context import (
    MarketContextSnapshot,
    SymbolThemeMembership,
    Theme,
)


class MarketContextSnapshotRepository:
    """market_context_snapshots 조회/생성 레포지토리."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, **kwargs) -> MarketContextSnapshot:
        snapshot = MarketContextSnapshot(**kwargs)
        self._session.add(snapshot)
        await self._session.flush()
        return snapshot

    async def get(self, snapshot_id: int) -> MarketContextSnapshot | None:
        return await self._session.get(MarketContextSnapshot, snapshot_id)

    async def list_recent(
        self, market: MarketCode | None = None, limit: int = 50
    ) -> list[MarketContextSnapshot]:
        stmt = select(MarketContextSnapshot).order_by(
            MarketContextSnapshot.captured_at.desc(), MarketContextSnapshot.id.desc()
        )
        if market is not None:
            stmt = stmt.where(MarketContextSnapshot.market == market)
        stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ThemeRepository:
    """themes 조회/생성 레포지토리."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_code(self, market: MarketCode, code: str) -> Theme | None:
        result = await self._session.execute(
            select(Theme).where(Theme.market == market, Theme.code == code)
        )
        return result.scalar_one_or_none()

    async def create(self, market: MarketCode, code: str, name: str) -> Theme:
        theme = Theme(market=market, code=code, name=name)
        self._session.add(theme)
        await self._session.flush()
        return theme

    async def list_by_market(self, market: MarketCode | None = None) -> list[Theme]:
        stmt = select(Theme).order_by(Theme.market, Theme.code)
        if market is not None:
            stmt = stmt.where(Theme.market == market)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class SymbolThemeMembershipRepository:
    """symbol_theme_memberships 조회/생성 레포지토리."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def exists(self, symbol_code: str, theme_id: int) -> bool:
        result = await self._session.execute(
            select(SymbolThemeMembership.id).where(
                SymbolThemeMembership.symbol_code == symbol_code,
                SymbolThemeMembership.theme_id == theme_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def create(
        self, market: MarketCode, symbol_code: str, theme_id: int
    ) -> SymbolThemeMembership:
        membership = SymbolThemeMembership(
            market=market, symbol_code=symbol_code, theme_id=theme_id
        )
        self._session.add(membership)
        await self._session.flush()
        return membership

    async def list_themes_for_symbol(self, symbol_code: str) -> list[Theme]:
        result = await self._session.execute(
            select(Theme)
            .join(SymbolThemeMembership, SymbolThemeMembership.theme_id == Theme.id)
            .where(SymbolThemeMembership.symbol_code == symbol_code)
            .order_by(Theme.code)
        )
        return list(result.scalars().all())
