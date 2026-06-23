"""SEC EDGAR 공시 수집 provider (C-5.20) — 미국 공시(8-K/10-K/10-Q 등).

data.sec.gov 의 submissions API(회사별 최근 제출)와 company_tickers.json(티커→CIK)을
호출한다. 무료이며 키가 없다. 다만 SEC는 연락처가 담긴 User-Agent 헤더를 요구한다.
httpx client 주입으로 네트워크 없이 테스트 가능. 순수 파서 분리.

DART(한국)와 같은 read-only 수집 패턴 — 주문과 무관하다.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

# 티커→CIK 매핑(전체 상장사). 하루 한 번 정도만 바뀐다.
EDGAR_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
# 회사별 최근 제출. CIK는 10자리 zero-pad 필요(CIK0000320193).
EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
# 공시 인덱스 페이지(중복 수집 방지 dedup 키 + 사람이 열어볼 링크).
EDGAR_FILING_INDEX_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{accession}-index.htm"
)


class EdgarProviderError(Exception):
    """SEC EDGAR 조회 실패(네트워크/rate limit/User-Agent 누락 등)."""


@dataclass
class Filing:
    cik: int
    ticker: str | None
    form: str            # 8-K, 10-K, 10-Q, SC 13D, 4, ...
    accession_no: str    # 0000320193-24-000123
    filing_date: str     # YYYY-MM-DD
    report_date: str     # YYYY-MM-DD (없을 수 있음)
    primary_doc: str
    company_name: str = ""

    @property
    def url(self) -> str:
        return EDGAR_FILING_INDEX_URL.format(
            cik=self.cik,
            accession_nodash=self.accession_no.replace("-", ""),
            accession=self.accession_no,
        )


def parse_company_tickers(body: dict) -> dict[str, int]:
    """company_tickers.json 응답을 {ticker(대문자): cik} 로 파싱한다.

    응답은 {"0": {"cik_str": 320193, "ticker": "AAPL", ...}, ...} 형태(객체).
    """
    out: dict[str, int] = {}
    rows = body.values() if isinstance(body, dict) else body
    for row in rows:
        ticker = (row.get("ticker") or "").strip().upper()
        cik = row.get("cik_str")
        if ticker and cik is not None:
            out[ticker] = int(cik)
    return out


def parse_submissions(body: dict, *, ticker: str | None = None) -> list[Filing]:
    """submissions API 응답의 filings.recent(병렬 배열)을 Filing 목록으로 파싱한다."""
    cik_raw = body.get("cik")
    try:
        cik = int(cik_raw)
    except (TypeError, ValueError):
        return []
    company_name = body.get("name", "")
    recent = (body.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accnos = recent.get("accessionNumber") or []
    fdates = recent.get("filingDate") or []
    rdates = recent.get("reportDate") or []
    pdocs = recent.get("primaryDocument") or []

    out: list[Filing] = []
    for i, form in enumerate(forms):
        accno = accnos[i] if i < len(accnos) else None
        if not accno:
            continue
        out.append(Filing(
            cik=cik,
            ticker=ticker,
            form=form,
            accession_no=accno,
            filing_date=fdates[i] if i < len(fdates) else "",
            report_date=rdates[i] if i < len(rdates) else "",
            primary_doc=pdocs[i] if i < len(pdocs) else "",
            company_name=company_name,
        ))
    return out


class EdgarProvider:
    """SEC EDGAR submissions/ticker 조회. User-Agent(연락처) 필요."""

    def __init__(
        self,
        user_agent: str | None,
        *,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._user_agent = user_agent
        self._timeout = timeout_seconds
        self._client = client
        self._ticker_cache: dict[str, int] | None = None

    def _headers(self) -> dict[str, str]:
        # SEC는 연락처가 담긴 User-Agent를 요구한다(미설정 시 403/429).
        return {"User-Agent": self._user_agent or "", "Accept-Encoding": "gzip, deflate"}

    async def _get_json(self, url: str) -> dict:
        if not self._user_agent:
            raise EdgarProviderError("SEC_EDGAR_USER_AGENT is not set")
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns = self._client is None
        try:
            resp = await client.get(url, headers=self._headers())
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            raise EdgarProviderError(f"EDGAR request failed: {e}") from e
        finally:
            if owns:
                await client.aclose()

    async def ticker_to_cik(self, ticker: str) -> int | None:
        """티커→CIK. 첫 호출 때 company_tickers.json을 한 번 받아 캐시한다."""
        if self._ticker_cache is None:
            body = await self._get_json(EDGAR_TICKERS_URL)
            self._ticker_cache = parse_company_tickers(body)
        return self._ticker_cache.get(ticker.strip().upper())

    async def fetch_submissions(self, cik: int, ticker: str | None = None) -> list[Filing]:
        """회사(CIK)의 최근 제출 목록을 가져온다."""
        body = await self._get_json(EDGAR_SUBMISSIONS_URL.format(cik=cik))
        return parse_submissions(body, ticker=ticker)
