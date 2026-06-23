"""C-5.20 SEC EDGAR 공시 수집 테스트 (MockTransport, 네트워크 없음)."""
from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.domain.models.enums import MarketCode
from app.services.edgar_ingest_service import EdgarIngestService
from app.services.edgar_provider import (
    EdgarProvider,
    EdgarProviderError,
    parse_company_tickers,
    parse_submissions,
)
from app.services.news_context_service import NewsContextService
from app.trading.analysis.edgar_materiality import (
    CATEGORY_HIGH,
    CATEGORY_LOW,
    CATEGORY_MEDIUM,
    CATEGORY_NOISE,
    score_form_materiality,
)

from datetime import datetime

_TODAY = datetime.now(KST).date().strftime("%Y-%m-%d")

_TICKERS_BODY = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
}

_SUBMISSIONS_AAPL = {
    "cik": "320193",
    "name": "Apple Inc.",
    "tickers": ["AAPL"],
    "filings": {
        "recent": {
            "accessionNumber": ["0000320193-26-000010", "0000320193-26-000011",
                                "0000320193-26-000012"],
            "form": ["8-K", "4", "SC 13G"],
            "filingDate": [_TODAY, _TODAY, _TODAY],
            "reportDate": [_TODAY, "", ""],
            "primaryDocument": ["a8k.htm", "form4.xml", "sc13g.htm"],
            "primaryDocDescription": ["8-K", "FORM 4", "SC 13G"],
        }
    },
}


def _client() -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        # SEC는 User-Agent를 요구 — 테스트에서도 헤더가 실려 오는지 확인.
        assert request.headers.get("User-Agent")
        if "company_tickers.json" in url:
            return httpx.Response(200, json=_TICKERS_BODY)
        if "submissions/CIK0000320193" in url:
            return httpx.Response(200, json=_SUBMISSIONS_AAPL)
        return httpx.Response(404, json={})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# --- 중요도 점수(순수) -------------------------------------------------------
def test_form_materiality_categories() -> None:
    assert score_form_materiality("8-K") == (0.9, CATEGORY_HIGH)
    assert score_form_materiality("10-K") == (0.9, CATEGORY_HIGH)
    assert score_form_materiality("8-K/A")[1] == CATEGORY_HIGH  # 정정도 같은 유형
    assert score_form_materiality("SC 13D")[1] == CATEGORY_MEDIUM
    assert score_form_materiality("424B5")[1] == CATEGORY_MEDIUM
    assert score_form_materiality("4")[1] == CATEGORY_LOW       # 내부자 거래
    assert score_form_materiality("NT 10-Q")[1] == CATEGORY_NOISE


# --- 파서(순수) -------------------------------------------------------------
def test_parse_company_tickers() -> None:
    m = parse_company_tickers(_TICKERS_BODY)
    assert m["AAPL"] == 320193
    assert m["MSFT"] == 789019


def test_parse_submissions_fields() -> None:
    filings = parse_submissions(_SUBMISSIONS_AAPL, ticker="AAPL")
    assert len(filings) == 3
    assert filings[0].form == "8-K"
    assert filings[0].cik == 320193
    assert "0000320193-26-000010" in filings[0].url
    assert filings[0].url.startswith("https://www.sec.gov/Archives/edgar/data/320193/")


# --- provider (MockTransport) ----------------------------------------------
async def test_provider_missing_user_agent_raises() -> None:
    with pytest.raises(EdgarProviderError):
        await EdgarProvider(None, client=_client()).ticker_to_cik("AAPL")


async def test_provider_ticker_to_cik_caches() -> None:
    provider = EdgarProvider("ai-trading-platform test@example.com", client=_client())
    assert await provider.ticker_to_cik("aapl") == 320193  # 대소문자 무관
    assert await provider.ticker_to_cik("UNKNOWN") is None


# --- ingest 서비스 ----------------------------------------------------------
async def test_ingest_filters_by_form_materiality(db_session: AsyncSession) -> None:
    provider = EdgarProvider("ai-trading-platform test@example.com", client=_client())
    svc = EdgarIngestService(db_session, provider=provider)
    # AAPL: 8-K(high) + SC 13G(medium) 저장, Form 4(low<0.5)는 제외.
    summary = await svc.ingest(symbols=["AAPL"], min_score=0.5)

    assert summary.resolved == 1
    assert summary.fetched == 3
    assert summary.material == 2   # 8-K + SC 13G
    assert summary.created == 2

    news = await NewsContextService(db_session).list_news(symbol_code="AAPL")
    assert len(news) == 2
    assert all(n.source == "edgar" for n in news)
    assert all(n.market == MarketCode.US for n in news)


async def test_ingest_unresolved_ticker(db_session: AsyncSession) -> None:
    provider = EdgarProvider("ai-trading-platform test@example.com", client=_client())
    svc = EdgarIngestService(db_session, provider=provider)
    summary = await svc.ingest(symbols=["NOPE"], min_score=0.5)
    assert summary.resolved == 0
    assert summary.unresolved == ["NOPE"]
    assert summary.created == 0


async def test_ingest_dedup(db_session: AsyncSession) -> None:
    provider = EdgarProvider("ai-trading-platform test@example.com", client=_client())
    svc = EdgarIngestService(db_session, provider=provider)
    first = await svc.ingest(symbols=["AAPL"], min_score=0.5)
    second = await svc.ingest(symbols=["AAPL"], min_score=0.5)
    assert first.created == 2
    assert second.created == 0  # 같은 accession url → 중복 저장 안 함
    assert second.skipped_existing == 2
