from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from app.common.timezone import KST

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import MarketCode
from app.domain.repositories.news_context import NewsEventRepository
from app.domain.repositories.watchlist import WatchlistSymbolRepository
from app.services.dart_provider import DartProvider
from app.trading.analysis.news_materiality import score_materiality



@dataclass
class DartIngestSummary:
    fetched: int
    matched: int      # 모니터 종목에 해당
    material: int     # 중요도 임계 이상
    created: int      # 새로 저장
    skipped_existing: int

    def to_dict(self) -> dict:
        return {
            "fetched": self.fetched, "matched": self.matched, "material": self.material,
            "created": self.created, "skipped_existing": self.skipped_existing,
        }


class DartIngestService:
    """DART 최근 공시를 가져와 모니터 종목·중요도로 필터해 news_events에 저장한다 (C-2.59).

    "주가에 영향 없는 공시는 거른다" — 공시명(report_nm)을 중요도(C-2.57)로 점수화해 노이즈
    제거. 보유/관심 종목만 본다. url(rcpNo)로 중복 수집을 막는다. 주문과 무관한 read-only 수집.
    """

    def __init__(self, session: AsyncSession, provider: DartProvider | None = None) -> None:
        self._session = session
        self._news_repo = NewsEventRepository(session)
        if provider is None:
            from app.core.config import get_settings

            s = get_settings()
            provider = DartProvider(
                s.dart_api_key, timeout_seconds=s.dart_provider_timeout_seconds
            )
        self._provider = provider

    async def _watchlist_symbols(self) -> set[str]:
        return set(await WatchlistSymbolRepository(self._session).list_enabled_symbol_codes())

    async def ingest(
        self,
        symbols: list[str] | None = None,
        trading_day: date | None = None,
        min_score: float = 0.5,
    ) -> DartIngestSummary:
        monitored = set(symbols) if symbols is not None else await self._watchlist_symbols()
        day = trading_day or datetime.now(KST).date()

        disclosures = await self._provider.fetch_disclosures(day, day)

        matched = [d for d in disclosures if d.stock_code and d.stock_code in monitored]
        material = [d for d in matched if score_materiality(d.report_nm)[0] >= min_score]

        urls = [d.url for d in material]
        existing = await self._news_repo.existing_urls(urls)

        created = 0
        for d in material:
            if d.url in existing:
                continue
            score, category = score_materiality(d.report_nm)
            await self._news_repo.create(
                market=MarketCode.KR,
                symbol_code=d.stock_code,
                source="dart",
                headline=d.report_nm,
                url=d.url,
                published_at=self._published_at(d.rcept_dt),
                raw_payload={"rcept_no": d.rcept_no, "corp_name": d.corp_name,
                             "materiality": score, "category": category},
            )
            existing.add(d.url)
            created += 1
        await self._session.commit()

        return DartIngestSummary(
            fetched=len(disclosures), matched=len(matched), material=len(material),
            created=created, skipped_existing=len(material) - created,
        )

    @staticmethod
    def _published_at(rcept_dt: str) -> datetime:
        try:
            return datetime.strptime(rcept_dt, "%Y%m%d").replace(tzinfo=KST)
        except (ValueError, TypeError):
            return datetime.now(KST)
