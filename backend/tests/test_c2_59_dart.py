"""C-2.59 DART 공시 수집 테스트 (MockTransport, 네트워크 없음)."""

from datetime import date

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import MarketCode
from app.services.dart_ingest_service import DartIngestService
from app.services.dart_provider import DartProvider, DartProviderError, parse_dart_list
from app.services.news_context_service import NewsContextService

_LIST_BODY = {
    "status": "000", "message": "정상",
    "list": [
        {"rcept_no": "20260620000001", "stock_code": "005930", "corp_name": "삼성전자",
         "report_nm": "주요사항보고서(자기주식취득결정)", "rcept_dt": "20260620"},
        {"rcept_no": "20260620000002", "stock_code": "005930", "corp_name": "삼성전자",
         "report_nm": "[기재정정] IR 일정 안내", "rcept_dt": "20260620"},  # noise → 제외
        {"rcept_no": "20260620000003", "stock_code": "000660", "corp_name": "SK하이닉스",
         "report_nm": "단일판매ㆍ공급계약체결", "rcept_dt": "20260620"},  # 다른 종목
    ],
}


def _client(body=_LIST_BODY, status_code=200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "opendart.fss.or.kr" in str(request.url)
        return httpx.Response(status_code, json=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# --- 파서 -------------------------------------------------------------------
def test_parse_status_no_data_is_empty() -> None:
    assert parse_dart_list({"status": "013", "message": "데이터 없음"}) == []


def test_parse_error_raises() -> None:
    with pytest.raises(DartProviderError):
        parse_dart_list({"status": "020", "message": "사용한도 초과"})


def test_parse_extracts_fields() -> None:
    items = parse_dart_list(_LIST_BODY)
    assert len(items) == 3
    assert items[0].stock_code == "005930"
    assert "20260620000001" in items[0].url


# --- provider (MockTransport) ----------------------------------------------
async def test_provider_missing_key_raises() -> None:
    with pytest.raises(DartProviderError):
        await DartProvider(None, client=_client()).fetch_disclosures(
            date(2026, 6, 20), date(2026, 6, 20)
        )


# --- ingest 서비스 ----------------------------------------------------------
async def test_ingest_filters_symbol_and_materiality(db_session: AsyncSession) -> None:
    provider = DartProvider("fake-key", client=_client())
    svc = DartIngestService(db_session, provider=provider)
    # 005930만 모니터 → 000660 제외, noise(IR정정) 제외 → 1건만 저장
    summary = await svc.ingest(symbols=["005930"], trading_day=date(2026, 6, 20))

    assert summary.fetched == 3
    assert summary.matched == 2   # 005930 두 건
    assert summary.material == 1  # 자기주식취득(고중요)만
    assert summary.created == 1

    news = await NewsContextService(db_session).list_news(symbol_code="005930")
    assert len(news) == 1
    assert news[0].source == "dart"
    assert "자기주식취득" in news[0].headline


async def test_ingest_dedup(db_session: AsyncSession) -> None:
    provider = DartProvider("fake-key", client=_client())
    svc = DartIngestService(db_session, provider=provider)
    first = await svc.ingest(symbols=["005930"], trading_day=date(2026, 6, 20))
    second = await svc.ingest(symbols=["005930"], trading_day=date(2026, 6, 20))
    assert first.created == 1
    assert second.created == 0  # 같은 rcpNo url → 중복 저장 안 함
    assert second.skipped_existing == 1
