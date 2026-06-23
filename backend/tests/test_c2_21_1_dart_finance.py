"""C-2.21.1 DART XBRL 재무제표 수집 테스트 (MockTransport, 네트워크 없음)."""
from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dart_finance_provider import (
    DartFinanceProvider,
    DartFinanceProviderError,
    FinanceItem,
    extract_key_items,
    parse_finstat_body,
)

# ── 픽스처 페이로드 ────────────────────────────────────────────────────────────

_COMPANY_BODY = {
    "status": "000",
    "corp_code": "00126380",
    "stock_code": "005930",
    "corp_name": "삼성전자",
}

_FINSTAT_BODY = {
    "status": "000",
    "list": [
        {"account_nm": "매출액", "thstrm_amount": "302,231,360,000,000",
         "frmtrm_amount": "259,000,000,000,000", "bfefrmtrm_amount": ""},
        {"account_nm": "영업이익", "thstrm_amount": "6,566,966,000,000",
         "frmtrm_amount": "43,376,000,000,000", "bfefrmtrm_amount": ""},
        {"account_nm": "당기순이익", "thstrm_amount": "15,487,000,000,000",
         "frmtrm_amount": "39,243,000,000,000", "bfefrmtrm_amount": ""},
        {"account_nm": "자산총계", "thstrm_amount": "455,905,000,000,000",
         "frmtrm_amount": "426,609,000,000,000", "bfefrmtrm_amount": ""},
        {"account_nm": "자본총계", "thstrm_amount": "306,969,000,000,000",
         "frmtrm_amount": "294,496,000,000,000", "bfefrmtrm_amount": ""},
        {"account_nm": "기타항목(무시)", "thstrm_amount": "99,999",
         "frmtrm_amount": "", "bfefrmtrm_amount": ""},
    ],
}

_EMPTY_BODY = {"status": "013", "message": "데이터 없음"}
_ERROR_BODY = {"status": "020", "message": "사용한도 초과"}


def _make_client(
    company_body: dict = _COMPANY_BODY,
    finstat_body: dict = _FINSTAT_BODY,
) -> httpx.AsyncClient:
    """company.json / fnlttSinglAcnt.json 요청을 URL 경로로 구분해 Mock 응답."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert "opendart.fss.or.kr" in str(request.url)
        if "company.json" in str(request.url):
            return httpx.Response(200, json=company_body)
        return httpx.Response(200, json=finstat_body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ── 파서 단위 테스트 ────────────────────────────────────────────────────────────

def test_parse_empty_returns_empty() -> None:
    assert parse_finstat_body(_EMPTY_BODY) == []


def test_parse_error_raises() -> None:
    with pytest.raises(DartFinanceProviderError):
        parse_finstat_body(_ERROR_BODY)


def test_parse_extracts_items() -> None:
    items = parse_finstat_body(_FINSTAT_BODY)
    assert len(items) == 6
    assert items[0].account_nm == "매출액"
    assert items[0].thstrm_amount == "302,231,360,000,000"


def test_extract_key_items_maps_correctly() -> None:
    items = parse_finstat_body(_FINSTAT_BODY)
    ki = extract_key_items(items)
    assert ki["revenue"] == 302_231_360_000_000
    assert ki["operating_income"] == 6_566_966_000_000
    assert ki["net_income"] == 15_487_000_000_000
    assert ki["total_assets"] == 455_905_000_000_000
    assert ki["total_equity"] == 306_969_000_000_000
    assert "기타항목(무시)" not in ki


def test_extract_key_items_skips_unmapped() -> None:
    items = [FinanceItem("알수없는항목", "100,000", None, None)]
    ki = extract_key_items(items)
    assert ki == {}


def test_extract_key_items_handles_none_amount() -> None:
    items = [FinanceItem("매출액", None, None, None)]
    ki = extract_key_items(items)
    assert ki["revenue"] is None


# ── Provider (MockTransport) ────────────────────────────────────────────────

async def test_provider_missing_api_key_raises() -> None:
    provider = DartFinanceProvider(None, client=_make_client())
    with pytest.raises(DartFinanceProviderError, match="DART_API_KEY"):
        await provider.fetch_corp_code("005930")


async def test_provider_fetch_corp_code() -> None:
    provider = DartFinanceProvider("test-key", client=_make_client())
    corp_code = await provider.fetch_corp_code("005930")
    assert corp_code == "00126380"


async def test_provider_fetch_statements_returns_items() -> None:
    provider = DartFinanceProvider("test-key", client=_make_client())
    items = await provider.fetch_statements("00126380", "2023")
    assert len(items) == 6
    assert items[0].account_nm == "매출액"


async def test_provider_fetch_statements_empty() -> None:
    client = _make_client(finstat_body=_EMPTY_BODY)
    provider = DartFinanceProvider("test-key", client=client)
    items = await provider.fetch_statements("00126380", "2023")
    assert items == []


async def test_provider_company_error_raises() -> None:
    bad_company = {"status": "010", "message": "등록되지 않은 키"}
    provider = DartFinanceProvider("bad-key", client=_make_client(company_body=bad_company))
    with pytest.raises(DartFinanceProviderError):
        await provider.fetch_corp_code("005930")


# ── 인제스트 서비스 (DB 통합) ──────────────────────────────────────────────────

async def test_ingest_upserts_record(db_session: AsyncSession) -> None:
    """수집 결과가 financial_statements 테이블에 저장되는지 검증한다."""
    from app.domain.repositories.financial_statement import FinancialStatementRepository
    from app.services.dart_finance_ingest_service import DartFinanceIngestService

    client = _make_client()
    provider = DartFinanceProvider("test-key", client=client)
    svc = DartFinanceIngestService(db_session, provider=provider)

    summary = await svc.ingest(symbols=["005930"], bsns_years=["2023"])

    assert summary.symbols_attempted == 1
    assert summary.symbols_ok == 1
    assert summary.symbols_failed == 0
    assert summary.records_upserted >= 1

    repo = FinancialStatementRepository(db_session)
    row = await repo.get_latest_annual("005930")
    assert row is not None
    assert row.corp_code == "00126380"
    assert row.key_items is not None
    assert row.key_items.get("revenue") == 302_231_360_000_000


async def test_ingest_upsert_is_idempotent(db_session: AsyncSession) -> None:
    """동일 종목·연도를 두 번 수집해도 중복 생성되지 않음."""
    from app.domain.repositories.financial_statement import FinancialStatementRepository
    from app.services.dart_finance_ingest_service import DartFinanceIngestService

    client = _make_client()
    provider = DartFinanceProvider("test-key", client=client)
    svc = DartFinanceIngestService(db_session, provider=provider)

    await svc.ingest(symbols=["005930"], bsns_years=["2023"])
    await svc.ingest(symbols=["005930"], bsns_years=["2023"])

    repo = FinancialStatementRepository(db_session)
    rows = await repo.list_by_stock_code("005930")
    corp_period_keys = {(r.corp_code, r.bsns_year, r.reprt_code, r.fs_div) for r in rows}
    # 같은 (corp_code, bsns_year, reprt_code, fs_div) 조합은 1개만 존재해야 한다
    assert len(corp_period_keys) == len(rows)


async def test_ingest_handles_provider_error_gracefully(db_session: AsyncSession) -> None:
    """corp_code 조회 실패 종목은 errors에 기록되고 나머지는 계속 진행된다."""
    from app.services.dart_finance_ingest_service import DartFinanceIngestService

    bad_company = {"status": "010", "message": "등록되지 않은 키"}
    client = _make_client(company_body=bad_company)
    provider = DartFinanceProvider("test-key", client=client)
    svc = DartFinanceIngestService(db_session, provider=provider)

    summary = await svc.ingest(symbols=["999999"], bsns_years=["2023"])

    assert summary.symbols_failed == 1
    assert len(summary.errors) == 1
