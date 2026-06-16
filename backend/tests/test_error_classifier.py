import httpx

from app.trading.broker.error_classifier import (
    KIS_ERROR_CONNECTION_TIMEOUT,
    KIS_ERROR_INSUFFICIENT_BALANCE,
    KIS_ERROR_INVALID_PRICE_TICK,
    KIS_ERROR_MARKET_CLOSED,
    KIS_ERROR_NETWORK,
    KIS_ERROR_RATE_LIMIT,
    KIS_ERROR_SERVER_DISCONNECT,
    KIS_ERROR_TOKEN,
    KIS_ERROR_UNKNOWN,
    classify_exception,
    classify_kis_error,
    exc_message,
)
from app.trading.broker.exceptions import KISAPIError


def test_classify_token_error_by_msg_cd() -> None:
    assert classify_kis_error(KISAPIError("EGW00121", "기간이 만료된 token 입니다")) == KIS_ERROR_TOKEN


def test_classify_token_error_by_keyword() -> None:
    assert classify_kis_error(KISAPIError("1", "유효하지 않은 토큰 입니다")) == KIS_ERROR_TOKEN


def test_classify_rate_limit_error() -> None:
    assert classify_kis_error(KISAPIError("EGW00201", "초당 거래건수를 초과하였습니다")) == KIS_ERROR_RATE_LIMIT


def test_classify_market_closed_error() -> None:
    assert classify_kis_error(KISAPIError("1", "장운영시간이 아닙니다")) == KIS_ERROR_MARKET_CLOSED


def test_classify_insufficient_balance_error() -> None:
    assert classify_kis_error(KISAPIError("1", "주문가능금액이 부족합니다")) == KIS_ERROR_INSUFFICIENT_BALANCE


def test_classify_invalid_price_tick_error() -> None:
    assert (
        classify_kis_error(KISAPIError("1", "모의투자 주문처리가 안되었습니다(호가단위 오류)"))
        == KIS_ERROR_INVALID_PRICE_TICK
    )


def test_classify_unknown_error() -> None:
    assert classify_kis_error(KISAPIError("1", "알 수 없는 오류")) == KIS_ERROR_UNKNOWN


def test_classify_exception_kis_api_error() -> None:
    assert classify_exception(KISAPIError("EGW00201", "초당 거래건수를 초과하였습니다")) == KIS_ERROR_RATE_LIMIT


def test_classify_exception_read_timeout() -> None:
    request = httpx.Request("GET", "https://example.com")
    assert classify_exception(httpx.ReadTimeout("", request=request)) == KIS_ERROR_CONNECTION_TIMEOUT


def test_classify_exception_remote_protocol_error() -> None:
    assert classify_exception(httpx.RemoteProtocolError("Server disconnected")) == KIS_ERROR_SERVER_DISCONNECT


def test_classify_exception_generic() -> None:
    assert classify_exception(RuntimeError("some error")) == KIS_ERROR_UNKNOWN


def test_exc_message_non_empty() -> None:
    assert exc_message(RuntimeError("boom")) == "boom"


def test_exc_message_empty_falls_back_to_class_name() -> None:
    assert exc_message(RuntimeError()) == "RuntimeError"


def test_exc_message_timeout_falls_back_to_class_name() -> None:
    request = httpx.Request("GET", "https://example.com")
    msg = exc_message(httpx.ReadTimeout("", request=request))
    assert msg  # 빈 문자열이 아닌지 확인
