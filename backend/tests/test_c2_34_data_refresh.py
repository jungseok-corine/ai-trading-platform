"""C-2.34 Scheduled Data Refresh 테스트 (수급 자동 수집 오케스트레이션)."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.watchlist import Watchlist, WatchlistSymbol
from app.services.data_refresh_service import DataRefreshService


class _FakeFlowService:
    """InvestorFlowService.fetch_and_store를 흉내내는 테스트용 스텁.

    fail_symbols에 든 종목은 예외를 던지고, 나머지는 rows_per_symbol개의 더미 row를 반환한다.
    """

    def __init__(self, fail_symbols: set[str] | None = None, rows_per_symbol: int = 2) -> None:
        self.fail_symbols = fail_symbols or set()
        self.rows_per_symbol = rows_per_symbol
        self.calls: list[tuple[str, date, date]] = []

    async def fetch_and_store(self, symbol_code: str, date_from: date, date_to: date):
        self.calls.append((symbol_code, date_from, date_to))
        if symbol_code in self.fail_symbols:
            raise RuntimeError(f"KIS error for {symbol_code}")
        return list(range(self.rows_per_symbol))  # 더미 rows


async def test_refresh_isolates_failures(db_session: AsyncSession) -> None:
    fake = _FakeFlowService(fail_symbols={"000660"})
    service = DataRefreshService(db_session, fake)  # type: ignore[arg-type]

    summary = await service.refresh_investor_flows(
        ["005930", "000660", "035720"], date_from=date(2026, 6, 10), date_to=date(2026, 6, 15)
    )

    assert summary.requested == 3
    assert summary.succeeded == 2
    assert summary.failed == 1
    assert summary.rows == 4  # 성공 2종목 * 2 rows
    assert "000660" in summary.errors
    # 실패해도 나머지 종목은 모두 호출됨
    assert {c[0] for c in fake.calls} == {"005930", "000660", "035720"}


async def test_refresh_defaults_lookback_dates(db_session: AsyncSession) -> None:
    fake = _FakeFlowService()
    service = DataRefreshService(db_session, fake)  # type: ignore[arg-type]

    await service.refresh_investor_flows(["005930"], lookback_days=5)
    symbol, date_from, date_to = fake.calls[0]
    assert (date_to - date_from).days == 5


async def test_watchlist_symbols_only_enabled(db_session: AsyncSession) -> None:
    # enabled watchlist + enabled 종목
    wl = Watchlist(name="active", enabled=True)
    db_session.add(wl)
    await db_session.commit()
    db_session.add_all([
        WatchlistSymbol(watchlist_id=wl.id, symbol_code="005930", enabled=True),
        WatchlistSymbol(watchlist_id=wl.id, symbol_code="000660", enabled=False),  # 제외
    ])
    # disabled watchlist의 종목은 제외
    wl2 = Watchlist(name="off", enabled=False)
    db_session.add(wl2)
    await db_session.commit()
    db_session.add(WatchlistSymbol(watchlist_id=wl2.id, symbol_code="035720", enabled=True))
    await db_session.commit()

    service = DataRefreshService(db_session, _FakeFlowService())  # type: ignore[arg-type]
    symbols = await service.watchlist_symbols()
    assert symbols == ["005930"]
