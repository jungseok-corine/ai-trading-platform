"""Phase 2: KIS 모의투자 해외주식(미국장) 주문/잔고 브로커 검증.

실제 KIS 서버에 요청하지 않는다 — _request / quotes_client를 mock으로 대체한다.
안전: 모의투자(VTS) tr_id만 사용하고, 주문 API는 재시도하지 않는다(중복주문 방지).
"""
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from app.domain.models.enums import OrderStatus, TradeSide
from app.trading.broker.kis_overseas_paper import (
    TR_ID_US_INQUIRE_BALANCE,
    TR_ID_US_ORDER_BUY,
    TR_ID_US_ORDER_BUY_REAL,
    TR_ID_US_ORDER_SELL,
    TR_ID_US_ORDER_SELL_REAL,
    KISOverseasPaperBrokerClient,
    _to_ovrs_excg_cd,
)
from app.trading.broker.schemas import (
    MinuteCandle,
    OrderRequest,
    OrderType,
    PriceQuote,
)


def _make_broker(quotes=None) -> KISOverseasPaperBrokerClient:
    broker = KISOverseasPaperBrokerClient(
        account_no="50000000-01",
        quotes_client=quotes,
        base_url="https://openapivts.koreainvestment.com:29443",
        app_key="k",
        app_secret="s",
        http_client=AsyncMock(spec=httpx.AsyncClient),
        token_cache_path=Path("/tmp/test_overseas_paper_token.json"),
        rate_limit_min_interval_seconds=0.0,
        rate_limit_cooldown_seconds=0.0,
    )
    broker._get_access_token = AsyncMock(return_value="tok")  # type: ignore[method-assign]
    return broker


# --------------------------------------------------------------------------- #
# tr_id / 거래소 코드 매핑
# --------------------------------------------------------------------------- #


def test_paper_tr_ids_are_mock_and_asymmetric() -> None:
    # 모의 매수/매도 tr_id는 비대칭(KIS 문서)
    assert TR_ID_US_ORDER_BUY == "VTTT1002U"
    assert TR_ID_US_ORDER_SELL == "VTTT1001U"
    # 실전 상수는 정의돼 있으나 이 브로커는 사용하지 않는다(실거래 비활성 불변식)
    assert TR_ID_US_ORDER_BUY_REAL == "TTTT1002U"
    assert TR_ID_US_ORDER_SELL_REAL == "TTTT1006U"


def test_excd_to_ovrs_excg_mapping() -> None:
    assert _to_ovrs_excg_cd("NAS") == "NASD"
    assert _to_ovrs_excg_cd("NYS") == "NYSE"
    assert _to_ovrs_excg_cd("AMS") == "AMEX"
    assert _to_ovrs_excg_cd(None) == "NASD"  # 기본 NAS → NASD
    assert _to_ovrs_excg_cd("xxx") == "NASD"  # 알 수 없으면 NASD 폴백


# --------------------------------------------------------------------------- #
# place_order
# --------------------------------------------------------------------------- #


async def test_buy_order_uses_mock_buy_tr_id_and_maps_exchange() -> None:
    broker = _make_broker()
    broker._request = AsyncMock(return_value={"output": {"ODNO": "0030001", "KRX_FWDG_ORD_ORGNO": "01"}})

    result = await broker.place_order(
        OrderRequest(symbol_code="AAPL", side=TradeSide.BUY, quantity=3,
                     price=Decimal("190.50"), exchange="NAS")
    )

    assert result.broker_order_id == "0030001"
    assert result.order_status == OrderStatus.PENDING
    call = broker._request.call_args
    assert call.args[0] == "POST"
    assert call.args[1] == "/uapi/overseas-stock/v1/trading/order"
    assert call.kwargs["tr_id"] == TR_ID_US_ORDER_BUY
    body = call.kwargs["json_body"]
    assert body["OVRS_EXCG_CD"] == "NASD"
    assert body["PDNO"] == "AAPL"
    assert body["ORD_QTY"] == "3"
    assert body["OVRS_ORD_UNPR"] == "190.50"
    # 주문 API는 재시도하지 않는다 (중복주문 방지)
    assert call.kwargs["retryable"] is False


async def test_sell_order_uses_mock_sell_tr_id_and_nyse() -> None:
    broker = _make_broker()
    broker._request = AsyncMock(return_value={"output": {"ODNO": "0030002"}})

    await broker.place_order(
        OrderRequest(symbol_code="JPM", side=TradeSide.SELL, quantity=1,
                     price=Decimal("210"), exchange="NYS")
    )

    call = broker._request.call_args
    assert call.kwargs["tr_id"] == TR_ID_US_ORDER_SELL
    assert call.kwargs["json_body"]["OVRS_EXCG_CD"] == "NYSE"


async def test_market_order_rejected() -> None:
    broker = _make_broker()
    broker._request = AsyncMock()
    with pytest.raises(ValueError):
        await broker.place_order(
            OrderRequest(symbol_code="AAPL", side=TradeSide.BUY, quantity=1,
                         price=Decimal("1"), order_type=OrderType.MARKET)
        )
    broker._request.assert_not_called()


# --------------------------------------------------------------------------- #
# 잔고
# --------------------------------------------------------------------------- #


async def test_balance_parses_overseas_holdings() -> None:
    broker = _make_broker()
    broker._request = AsyncMock(return_value={
        "output1": [
            {"ovrs_pdno": "AAPL", "ovrs_item_name": "APPLE", "ovrs_cblc_qty": "5",
             "pchs_avg_pric": "180.0", "now_pric2": "190.0", "ovrs_stck_evlu_amt": "950.0",
             "frcr_evlu_pfls_amt": "50.0", "evlu_pfls_rt": "5.5"},
            {"ovrs_pdno": "TSLA", "ovrs_cblc_qty": "0", "pchs_avg_pric": "0",
             "now_pric2": "0", "ovrs_stck_evlu_amt": "0", "frcr_evlu_pfls_amt": "0",
             "evlu_pfls_rt": "0"},  # 수량 0 → 제외
        ],
        "output2": {"frcr_pchs_amt1": "900.0", "tot_evlu_pfls_amt": "950.0", "ovrs_tot_pfls": "50.0"},
    })

    balance = await broker.get_account_balance()

    assert [h.symbol_code for h in balance.holdings] == ["AAPL"]
    assert balance.holdings[0].quantity == 5
    assert balance.summary.total_profit_loss_amount == Decimal("50.0")
    call = broker._request.call_args
    assert call.kwargs["tr_id"] == TR_ID_US_INQUIRE_BALANCE
    assert call.kwargs["params"]["TR_CRCY_CD"] == "USD"


# --------------------------------------------------------------------------- #
# 시세 위임 (실전 도메인 read-only 클라이언트)
# --------------------------------------------------------------------------- #


async def test_price_and_candles_delegate_to_quotes_client() -> None:
    quotes = AsyncMock()
    quotes.get_overseas_price = AsyncMock(return_value=PriceQuote(
        symbol_code="AAPL", current_price=Decimal("190"), change=Decimal("1"),
        change_rate=Decimal("0.5"), open_price=Decimal("189"), high_price=Decimal("191"),
        low_price=Decimal("188"), volume=1000,
    ))
    quotes.get_overseas_minute_candles = AsyncMock(return_value=[MinuteCandle(
        business_date="20260622", trade_time="100000", open_price=Decimal("1"),
        high_price=Decimal("1"), low_price=Decimal("1"), close_price=Decimal("1"), volume=1,
    )])
    broker = _make_broker(quotes=quotes)

    price = await broker.get_current_price("AAPL")
    candles = await broker.get_minute_candles("AAPL")

    assert price.current_price == Decimal("190")
    assert len(candles) == 1
    quotes.get_overseas_price.assert_awaited_once()
    quotes.get_overseas_minute_candles.assert_awaited_once()


async def test_quotes_methods_raise_without_quotes_client() -> None:
    broker = _make_broker(quotes=None)
    with pytest.raises(NotImplementedError):
        await broker.get_current_price("AAPL")
    with pytest.raises(NotImplementedError):
        await broker.get_minute_candles("AAPL")
