"""C-4 주요종목 watchlist 시드 스크립트 테스트."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.watchlist import Watchlist, WatchlistSymbol

from scripts.seed_major_symbols_watchlist import _SYMBOLS, run

_NAME = "주요종목 (대형주)"


async def _symbol_count(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(WatchlistSymbol))).scalar_one())


async def test_symbol_codes_are_unique_and_6digit() -> None:
    codes = [c for c, _ in _SYMBOLS]
    assert len(codes) == len(set(codes))  # 중복 없음
    assert all(len(c) == 6 and c.isdigit() for c in codes)


async def test_dry_run_creates_nothing(db_session: AsyncSession) -> None:
    info = await run(db_session, apply=False, name=_NAME)
    assert len(info["to_add"]) == len(_SYMBOLS)
    assert await _symbol_count(db_session) == 0


async def test_apply_seeds_all_and_is_idempotent(db_session: AsyncSession) -> None:
    info1 = await run(db_session, apply=True, name=_NAME)
    assert info1["watchlist_created"] is True
    assert await _symbol_count(db_session) == len(_SYMBOLS)

    wl = (await db_session.execute(select(Watchlist).where(Watchlist.name == _NAME))).scalar_one()
    syms = (await db_session.execute(
        select(WatchlistSymbol).where(WatchlistSymbol.watchlist_id == wl.id)
    )).scalars().all()
    assert all(s.enabled for s in syms)
    assert {"005930", "247540"} <= {s.symbol_code for s in syms}

    # 재실행 멱등: 추가 0, 총량 동일
    info2 = await run(db_session, apply=True, name=_NAME)
    assert info2["watchlist_created"] is False
    assert info2["to_add"] == []
    assert await _symbol_count(db_session) == len(_SYMBOLS)
