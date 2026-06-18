"""C-2.18: 투자자 수급 데이터 Foundation 테스트.

실제 KIS API를 호출하지 않는다. 모든 KIS 응답은 mock 또는 직접 구성한 dict.
주문 API(place_order, TTTC0012U, VTTC0012U 등)는 일절 호출하지 않는다.
"""
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.investor_flow import InvestorFlow
from app.main import app
from app.services.investor_flow_service import (
    InvestorFlowService,
    _safe_decimal,
    _safe_int,
    parse_investor_flow_row,
)
from app.trading.broker.exceptions import KISAPIError
from app.trading.broker.kis_investor_flow_client import KISInvestorFlowClient


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _make_raw_row(
    date_str: str = "20260617",
    frgn_qty: str = "150000",
    frgn_pbmn: str = "3500",
    orgn_qty: str = "80000",
    orgn_pbmn: str = "1800",
    prsn_qty: str = "-230000",
    prsn_pbmn: str = "-5000",
) -> dict:
    return {
        "stck_bsop_date": date_str,
        "frgn_ntby_qty": frgn_qty,
        "frgn_ntby_tr_pbmn": frgn_pbmn,
        "orgn_ntby_qty": orgn_qty,
        "orgn_ntby_tr_pbmn": orgn_pbmn,
        "prsn_ntby_qty": prsn_qty,
        "prsn_ntby_tr_pbmn": prsn_pbmn,
        "stck_clpr": "75000",
    }


def _make_client(rows: list[dict]) -> KISInvestorFlowClient:
    """KIS API 응답을 mocking한 가짜 클라이언트."""
    client = MagicMock(spec=KISInvestorFlowClient)
    client.get_daily_investor_flow_by_stock = AsyncMock(return_value=rows)
    return client


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


# ---------------------------------------------------------------------------
# 1. KIS investor flow response parsing
# ---------------------------------------------------------------------------


def test_parse_investor_flow_row_basic() -> None:
    row = _make_raw_row()
    result = parse_investor_flow_row("005930", row)

    assert result["symbol_code"] == "005930"
    assert result["trade_date"] == date(2026, 6, 17)
    assert result["foreign_net_buy_quantity"] == 150000
    assert result["foreign_net_buy_amount"] == Decimal("3500")
    assert result["institution_net_buy_quantity"] == 80000
    assert result["institution_net_buy_amount"] == Decimal("1800")
    assert result["individual_net_buy_quantity"] == -230000
    assert result["individual_net_buy_amount"] == Decimal("-5000")
    assert result["source"] == "kis"
    assert result["raw_payload"]["stck_clpr"] == "75000"


def test_parse_investor_flow_row_negative_foreign() -> None:
    """외국인 순매도(음수) 파싱."""
    row = _make_raw_row(frgn_qty="-500000", frgn_pbmn="-12000")
    result = parse_investor_flow_row("000660", row)
    assert result["foreign_net_buy_quantity"] == -500000
    assert result["foreign_net_buy_amount"] == Decimal("-12000")


# ---------------------------------------------------------------------------
# 2. numeric string → Decimal/int 변환
# ---------------------------------------------------------------------------


def test_safe_int_positive() -> None:
    assert _safe_int("12345") == 12345


def test_safe_int_negative() -> None:
    assert _safe_int("-67890") == -67890


def test_safe_int_empty() -> None:
    assert _safe_int("") is None
    assert _safe_int(None) is None


def test_safe_int_comma_formatted() -> None:
    assert _safe_int("1,234,567") == 1234567


def test_safe_decimal_positive() -> None:
    assert _safe_decimal("3500") == Decimal("3500")


def test_safe_decimal_negative() -> None:
    assert _safe_decimal("-1800") == Decimal("-1800")


def test_safe_decimal_empty() -> None:
    assert _safe_decimal("") is None
    assert _safe_decimal(None) is None


# ---------------------------------------------------------------------------
# 3. empty response 처리
# ---------------------------------------------------------------------------


async def test_fetch_and_store_empty_response(db_session: AsyncSession) -> None:
    """KIS가 빈 output2를 반환하면 저장 없이 빈 배열을 반환해야 한다."""
    client = _make_client([])
    service = InvestorFlowService(session=db_session, client=client)

    result = await service.fetch_and_store(
        "005930", date(2026, 6, 10), date(2026, 6, 17)
    )
    assert result == []


# ---------------------------------------------------------------------------
# 4. KIS error response 처리
# ---------------------------------------------------------------------------


async def test_fetch_and_store_kis_error(db_session: AsyncSession) -> None:
    """KIS API 오류 시 KISAPIError가 그대로 전파되어야 한다."""
    client = MagicMock(spec=KISInvestorFlowClient)
    client.get_daily_investor_flow_by_stock = AsyncMock(
        side_effect=KISAPIError("EGW00001", "인증 오류")
    )
    service = InvestorFlowService(session=db_session, client=client)

    with pytest.raises(KISAPIError, match="EGW00001"):
        await service.fetch_and_store("005930", date(2026, 6, 17), date(2026, 6, 17))


# ---------------------------------------------------------------------------
# 5. InvestorFlow unique constraint / upsert
# ---------------------------------------------------------------------------


async def test_upsert_updates_existing_row(db_session: AsyncSession) -> None:
    """동일 symbol_code + trade_date가 이미 존재하면 기존 행을 갱신한다."""
    rows_v1 = [_make_raw_row(frgn_qty="100000", frgn_pbmn="2000")]
    service_v1 = InvestorFlowService(session=db_session, client=_make_client(rows_v1))
    result_v1 = await service_v1.fetch_and_store(
        "005930", date(2026, 6, 17), date(2026, 6, 17)
    )
    assert len(result_v1) == 1

    rows_v2 = [_make_raw_row(frgn_qty="200000", frgn_pbmn="5000")]
    service_v2 = InvestorFlowService(session=db_session, client=_make_client(rows_v2))
    result_v2 = await service_v2.fetch_and_store(
        "005930", date(2026, 6, 17), date(2026, 6, 17)
    )
    assert len(result_v2) == 1
    assert result_v2[0].foreign_net_buy_quantity == 200000
    assert result_v2[0].foreign_net_buy_amount == Decimal("5000")


# ---------------------------------------------------------------------------
# 6. fetch_and_store creates row
# ---------------------------------------------------------------------------


async def test_fetch_and_store_creates_row(db_session: AsyncSession) -> None:
    rows = [_make_raw_row(date_str="20260616")]
    service = InvestorFlowService(session=db_session, client=_make_client(rows))

    result = await service.fetch_and_store(
        "005930", date(2026, 6, 16), date(2026, 6, 16)
    )
    assert len(result) == 1
    flow = result[0]
    assert flow.symbol_code == "005930"
    assert flow.trade_date == date(2026, 6, 16)
    assert flow.foreign_net_buy_quantity == 150000
    assert flow.source == "kis"
    assert isinstance(flow.raw_payload, dict)


# ---------------------------------------------------------------------------
# 7. fetch_and_store updates existing row (확장 테스트)
# ---------------------------------------------------------------------------


async def test_fetch_and_store_stores_multiple_dates(db_session: AsyncSession) -> None:
    """output2에 여러 날짜가 있을 때 date_from~date_to 범위 내 행만 저장한다."""
    rows = [
        _make_raw_row(date_str="20260614"),  # 범위 밖
        _make_raw_row(date_str="20260615"),
        _make_raw_row(date_str="20260616"),
        _make_raw_row(date_str="20260617"),
    ]
    service = InvestorFlowService(session=db_session, client=_make_client(rows))

    result = await service.fetch_and_store(
        "005930", date(2026, 6, 15), date(2026, 6, 17)
    )
    assert len(result) == 3
    dates = {r.trade_date for r in result}
    assert date(2026, 6, 14) not in dates
    assert date(2026, 6, 15) in dates
    assert date(2026, 6, 16) in dates
    assert date(2026, 6, 17) in dates


# ---------------------------------------------------------------------------
# 8. list_by_symbol date range 테스트
# ---------------------------------------------------------------------------


async def test_list_by_symbol_date_range(db_session: AsyncSession) -> None:
    rows = [
        _make_raw_row(date_str="20260613"),
        _make_raw_row(date_str="20260614"),
        _make_raw_row(date_str="20260615"),
        _make_raw_row(date_str="20260616"),
    ]
    service = InvestorFlowService(session=db_session, client=_make_client(rows))
    await service.fetch_and_store("005930", date(2026, 6, 13), date(2026, 6, 16))

    results = await service.list_by_symbol(
        "005930", date_from=date(2026, 6, 14), date_to=date(2026, 6, 15)
    )
    assert len(results) == 2
    for r in results:
        assert date(2026, 6, 14) <= r.trade_date <= date(2026, 6, 15)


# ---------------------------------------------------------------------------
# 9. latest_by_symbol 테스트
# ---------------------------------------------------------------------------


async def test_latest_by_symbol_returns_most_recent(db_session: AsyncSession) -> None:
    rows = [
        _make_raw_row(date_str="20260610"),
        _make_raw_row(date_str="20260611"),
        _make_raw_row(date_str="20260612"),
    ]
    service = InvestorFlowService(session=db_session, client=_make_client(rows))
    await service.fetch_and_store("005930", date(2026, 6, 10), date(2026, 6, 12))

    latest = await service.latest_by_symbol("005930")
    assert latest is not None
    assert latest.trade_date == date(2026, 6, 12)


async def test_latest_by_symbol_no_data(db_session: AsyncSession) -> None:
    service = InvestorFlowService(session=db_session, client=_make_client([]))
    latest = await service.latest_by_symbol("999999")
    assert latest is None


# ---------------------------------------------------------------------------
# 10. API GET investor flows 테스트
# ---------------------------------------------------------------------------


async def test_api_get_investor_flows_empty(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    app.state.investor_flow_client = _make_client([])
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/investor-flows", params={"symbol_code": "005930"})
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        app.dependency_overrides.clear()


async def test_api_get_investor_flows_with_data(db_session: AsyncSession) -> None:
    """DB에 저장된 수급 데이터를 GET API로 조회한다."""
    rows = [_make_raw_row(date_str="20260617")]
    client = _make_client(rows)
    service = InvestorFlowService(session=db_session, client=client)
    await service.fetch_and_store("005930", date(2026, 6, 17), date(2026, 6, 17))

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    app.state.investor_flow_client = client
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client_http:
            resp = await client_http.get(
                "/api/v1/investor-flows",
                params={"symbol_code": "005930", "date_from": "2026-06-17", "date_to": "2026-06-17"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["symbol_code"] == "005930"
        assert data[0]["foreign_net_buy_quantity"] == 150000
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 11. API POST fetch 테스트
# ---------------------------------------------------------------------------


async def test_api_post_fetch_investor_flows(db_session: AsyncSession) -> None:
    rows = [_make_raw_row(date_str="20260617")]
    mock_client = _make_client(rows)

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    app.state.investor_flow_client = mock_client
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/investor-flows/fetch",
                json={
                    "symbol_code": "005930",
                    "date_from": "2026-06-17",
                    "date_to": "2026-06-17",
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["symbol_code"] == "005930"
        assert body["stored_count"] == 1
        assert len(body["flows"]) == 1
    finally:
        app.dependency_overrides.clear()


async def test_api_post_fetch_invalid_date_range(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    app.state.investor_flow_client = _make_client([])
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/investor-flows/fetch",
                json={
                    "symbol_code": "005930",
                    "date_from": "2026-06-20",
                    "date_to": "2026-06-17",  # date_from > date_to
                },
            )
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 12. unsupported provider 처리 테스트
# ---------------------------------------------------------------------------


def test_provider_unsupported_error_importable() -> None:
    """ProviderUnsupportedError 임포트 및 기본 동작을 확인한다."""
    from app.trading.broker.exceptions import ProviderUnsupportedError
    err = ProviderUnsupportedError("VTS does not support investor flow API")
    assert "VTS" in str(err)


def test_kis_investor_flow_client_class_exists() -> None:
    """KISInvestorFlowClient가 KISClientBase를 상속하는지 확인한다."""
    from app.trading.broker.kis_client import KISClientBase
    assert issubclass(KISInvestorFlowClient, KISClientBase)


# ---------------------------------------------------------------------------
# 13. 주문 API 미호출 테스트
# ---------------------------------------------------------------------------


def test_kis_investor_flow_client_has_no_place_order() -> None:
    """KISInvestorFlowClient에 place_order 메서드가 없어야 한다."""
    assert not hasattr(KISInvestorFlowClient, "place_order")


def test_investor_flow_service_has_no_order_methods() -> None:
    """InvestorFlowService에 주문 관련 메서드가 없어야 한다."""
    assert not hasattr(InvestorFlowService, "place_order")
    assert not hasattr(InvestorFlowService, "execute_signal")


# ---------------------------------------------------------------------------
# 14. parse_investor_flow_row 오류 처리
# ---------------------------------------------------------------------------


def test_parse_invalid_date_raises_value_error() -> None:
    """stck_bsop_date 형식이 잘못된 경우 ValueError를 발생시켜야 한다."""
    row = _make_raw_row()
    row["stck_bsop_date"] = "2026-06-17"  # 잘못된 형식 (YYYYMMDD가 아님)
    with pytest.raises(ValueError, match="stck_bsop_date"):
        parse_investor_flow_row("005930", row)


def test_parse_empty_qty_results_in_none() -> None:
    """빈 문자열 수량 필드는 None으로 파싱되어야 한다."""
    row = _make_raw_row(frgn_qty="", frgn_pbmn="")
    result = parse_investor_flow_row("005930", row)
    assert result["foreign_net_buy_quantity"] is None
    assert result["foreign_net_buy_amount"] is None


# ---------------------------------------------------------------------------
# 15. 전략 적용 제외 확인
# ---------------------------------------------------------------------------


def test_investor_flow_not_in_strategy_registry() -> None:
    """InvestorFlowService가 전략 레지스트리와 연결되지 않음을 확인한다."""
    from app.trading.strategy.registry import registered_types
    for strategy_type in registered_types():
        assert "investor" not in strategy_type.lower()
        assert "flow" not in strategy_type.lower()


def test_investor_flow_service_not_in_signal_service() -> None:
    """SignalService가 InvestorFlowService를 import하지 않음을 확인한다."""
    import importlib
    import inspect
    signal_service_module = importlib.import_module("app.services.signal_service")
    source = inspect.getsource(signal_service_module)
    assert "InvestorFlow" not in source
    assert "investor_flow" not in source
