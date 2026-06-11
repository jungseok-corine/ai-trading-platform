from app.trading.broker.error_classifier import (
    KIS_ERROR_INSUFFICIENT_BALANCE,
    KIS_ERROR_MARKET_CLOSED,
    KIS_ERROR_RATE_LIMIT,
    KIS_ERROR_TOKEN,
    KIS_ERROR_UNKNOWN,
    classify_kis_error,
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


def test_classify_unknown_error() -> None:
    assert classify_kis_error(KISAPIError("1", "알 수 없는 오류")) == KIS_ERROR_UNKNOWN
