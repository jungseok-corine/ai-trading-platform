"""DART XBRL 재무제표 수집·저장 서비스 (C-2.21.1).

watchlist 종목별로 corp_code를 조회한 뒤 최근 N개 사업연도의 재무제표를 수집한다.
중복은 upsert(기존 레코드 갱신)로 처리한다. read-only 수집이며 주문과 무관하다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.financial_statement import FinancialStatement
from app.domain.repositories.watchlist import WatchlistSymbolRepository
from app.services.dart_finance_provider import (
    DartFinanceProvider,
    DartFinanceProviderError,
    extract_key_items,
)


@dataclass
class FinanceIngestSummary:
    symbols_attempted: int
    symbols_ok: int
    symbols_failed: int
    records_upserted: int
    errors: list[str]

    def to_dict(self) -> dict:
        return {
            "symbols_attempted": self.symbols_attempted,
            "symbols_ok": self.symbols_ok,
            "symbols_failed": self.symbols_failed,
            "records_upserted": self.records_upserted,
            "errors": self.errors,
        }


class DartFinanceIngestService:
    """watchlist 종목별 DART XBRL 재무제표를 수집해 financial_statements에 저장한다.

    연결재무제표(CFS) 우선. CFS 데이터가 없으면 개별(OFS) 시도.
    """

    # 수집할 보고서 코드 순서: 사업보고서 → 반기보고서
    REPRT_CODES = ["11011", "11012"]
    # 수집할 사업연도 수 (최근 N년)
    DEFAULT_YEARS = 2

    def __init__(
        self,
        session: AsyncSession,
        provider: DartFinanceProvider | None = None,
    ) -> None:
        self._session = session
        if provider is None:
            from app.core.config import get_settings
            s = get_settings()
            provider = DartFinanceProvider(s.dart_api_key)
        self._provider = provider

    async def _watchlist_symbols(self) -> list[str]:
        return await WatchlistSymbolRepository(self._session).list_enabled_symbol_codes()

    async def ingest(
        self,
        symbols: list[str] | None = None,
        bsns_years: list[str] | None = None,
    ) -> FinanceIngestSummary:
        """symbols(미지정시 watchlist) 각각의 재무제표를 수집한다."""
        if symbols is None:
            symbols = await self._watchlist_symbols()
        if not bsns_years:
            from datetime import date
            current_year = date.today().year
            bsns_years = [str(current_year - i) for i in range(self.DEFAULT_YEARS)]

        ok = 0
        failed = 0
        records_upserted = 0
        errors: list[str] = []

        for symbol in symbols:
            try:
                corp_code, corp_name = await self._resolve_corp(symbol)
            except DartFinanceProviderError as e:
                failed += 1
                errors.append(f"{symbol}: corp_code 조회 실패 — {e}")
                continue

            for year in bsns_years:
                for reprt_code in self.REPRT_CODES:
                    upserted = await self._ingest_one(
                        symbol, corp_code, corp_name, year, reprt_code
                    )
                    records_upserted += upserted
            ok += 1

        await self._session.commit()
        return FinanceIngestSummary(
            symbols_attempted=len(symbols),
            symbols_ok=ok,
            symbols_failed=failed,
            records_upserted=records_upserted,
            errors=errors,
        )

    async def _resolve_corp(self, stock_code: str) -> tuple[str, str]:
        """stock_code → (corp_code, corp_name). Provider 통해 DART 조회."""
        corp_code = await self._provider.fetch_corp_code(stock_code)
        # company.json이 corp_name도 반환하지만 provider에서 미파싱 — 빈 문자열로 fallback.
        return corp_code, ""

    async def _ingest_one(
        self,
        stock_code: str,
        corp_code: str,
        corp_name: str,
        bsns_year: str,
        reprt_code: str,
    ) -> int:
        """단일 종목·연도·보고서 재무제표를 수집해 upsert한다. 반환: upsert된 레코드 수."""
        # CFS 우선, 없으면 OFS
        for fs_div in ("CFS", "OFS"):
            try:
                items = await self._provider.fetch_statements(
                    corp_code, bsns_year, reprt_code, fs_div
                )
            except DartFinanceProviderError:
                continue
            if not items:
                continue

            key_items = extract_key_items(items)
            if not key_items:
                continue

            await self._upsert(
                corp_code=corp_code,
                stock_code=stock_code,
                corp_name=corp_name,
                bsns_year=bsns_year,
                reprt_code=reprt_code,
                fs_div=fs_div,
                key_items=key_items,
                raw_count=len(items),
            )
            return 1  # CFS 성공 시 OFS 시도 안 함
        return 0

    async def _upsert(self, **kwargs: object) -> None:
        """INSERT … ON CONFLICT DO UPDATE (uq_finstat_corp_period 기반 upsert)."""
        stmt = (
            pg_insert(FinancialStatement)
            .values(**kwargs, collected_at=datetime.now(UTC))
            .on_conflict_do_update(
                constraint="uq_finstat_corp_period",
                set_={
                    "stock_code": kwargs["stock_code"],
                    "corp_name": kwargs["corp_name"],
                    "key_items": kwargs["key_items"],
                    "raw_count": kwargs["raw_count"],
                    "collected_at": datetime.now(UTC),
                },
            )
        )
        await self._session.execute(stmt)
