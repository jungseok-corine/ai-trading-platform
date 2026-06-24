from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.domain.models.enums import MarketCode
from app.domain.repositories.news_context import NewsEventRepository
from app.domain.repositories.watchlist import WatchlistSymbolRepository
from app.services.edgar_provider import EdgarProvider, Filing
from app.trading.analysis.edgar_materiality import score_form_materiality


@dataclass
class EdgarIngestSummary:
    fetched: int       # 가져온 제출 총합
    matched: int       # 모니터 종목에 해당(= fetched, 종목별 조회라 동일)
    material: int      # 중요도 임계 이상
    created: int       # 새로 저장
    skipped_existing: int
    resolved: int      # CIK 매핑에 성공한 종목 수
    unresolved: list[str]  # CIK를 못 찾은 티커

    def to_dict(self) -> dict:
        return {
            "fetched": self.fetched, "matched": self.matched, "material": self.material,
            "created": self.created, "skipped_existing": self.skipped_existing,
            "resolved": self.resolved, "unresolved": self.unresolved,
        }


class EdgarIngestService:
    """SEC EDGAR 최근 공시를 모니터 US 종목·유형 중요도로 필터해 news_events에 저장한다 (C-5.20).

    DART(한국)와 동형의 read-only 수집. 미국은 회사별 submissions를 조회하므로 모니터 종목을
    티커→CIK로 매핑한 뒤 종목별로 가져온다. form type 중요도로 노이즈를 거르고, url(인덱스
    페이지)로 중복 수집을 막는다. 주문과 무관하다.
    """

    def __init__(self, session: AsyncSession, provider: EdgarProvider | None = None) -> None:
        self._session = session
        self._news_repo = NewsEventRepository(session)
        if provider is None:
            from app.core.config import get_settings

            s = get_settings()
            provider = EdgarProvider(
                s.sec_edgar_user_agent,
                timeout_seconds=s.edgar_provider_timeout_seconds,
                min_request_interval_seconds=s.edgar_min_request_interval_seconds,
            )
        self._provider = provider

    async def _watchlist_us_symbols(self) -> list[str]:
        rows = await WatchlistSymbolRepository(self._session).list_enabled_symbols(market="US")
        return [code for (code, _market, _exchange) in rows]

    async def ingest(
        self,
        symbols: list[str] | None = None,
        since_days: int = 2,
        min_score: float = 0.5,
        max_symbols: int = 50,
    ) -> EdgarIngestSummary:
        """모니터 US 종목의 최근(since_days) 중요 공시를 수집한다.

        symbols=None이면 enabled watchlist의 US 종목을 대상으로 한다. SEC rate limit을
        고려해 종목 수를 max_symbols로 제한한다.
        """
        monitored = symbols if symbols is not None else await self._watchlist_us_symbols()
        monitored = monitored[:max_symbols]
        cutoff = (datetime.now(KST).date() - timedelta(days=max(since_days, 0)))

        fetched = 0
        resolved = 0
        unresolved: list[str] = []
        recent_material: list[Filing] = []

        for ticker in monitored:
            cik = await self._provider.ticker_to_cik(ticker)
            if cik is None:
                unresolved.append(ticker)
                continue
            resolved += 1
            filings = await self._provider.fetch_submissions(cik, ticker=ticker)
            fetched += len(filings)
            for f in filings:
                if self._filing_date(f.filing_date) < cutoff:
                    continue
                if score_form_materiality(f.form)[0] >= min_score:
                    recent_material.append(f)

        urls = [f.url for f in recent_material]
        existing = await self._news_repo.existing_urls(urls)

        created = 0
        for f in recent_material:
            if f.url in existing:
                continue
            score, category = score_form_materiality(f.form)
            await self._news_repo.create(
                market=MarketCode.US,
                symbol_code=f.ticker,
                source="edgar",
                headline=self._headline(f),
                url=f.url,
                published_at=self._published_at(f.filing_date),
                raw_payload={
                    "accession_no": f.accession_no, "form": f.form,
                    "company_name": f.company_name, "report_date": f.report_date,
                    "cik": f.cik, "materiality": score, "category": category,
                },
            )
            existing.add(f.url)
            created += 1
        await self._session.commit()

        return EdgarIngestSummary(
            fetched=fetched, matched=fetched, material=len(recent_material),
            created=created, skipped_existing=len(recent_material) - created,
            resolved=resolved, unresolved=unresolved,
        )

    @staticmethod
    def _headline(f: Filing) -> str:
        name = f.company_name or f.ticker or ""
        return f"[{f.form}] {name}".strip()

    @staticmethod
    def _filing_date(value: str) -> date:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return date.min

    @staticmethod
    def _published_at(value: str) -> datetime:
        try:
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=KST)
        except (ValueError, TypeError):
            return datetime.now(KST)
