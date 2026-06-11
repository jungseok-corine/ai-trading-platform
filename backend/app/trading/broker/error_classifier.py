from app.trading.broker.exceptions import KISAPIError

KIS_ERROR_TOKEN = "token_error"
KIS_ERROR_RATE_LIMIT = "rate_limit_or_repeated_call"
KIS_ERROR_MARKET_CLOSED = "market_closed"
KIS_ERROR_INSUFFICIENT_BALANCE = "insufficient_balance"
KIS_ERROR_UNKNOWN = "unknown"

_TOKEN_MSG_CDS = {"EGW00121", "EGW00123", "EGW00133"}
_RATE_LIMIT_MSG_CDS = {"EGW00201"}

_TOKEN_KEYWORDS = ("token", "토큰")
_RATE_LIMIT_KEYWORDS = ("초당", "거래건수", "rate limit")
_MARKET_CLOSED_KEYWORDS = ("장운영", "거래시간", "장마감", "장종료", "시간외")
_INSUFFICIENT_BALANCE_KEYWORDS = ("잔고", "예수금", "주문가능", "부족")


def classify_kis_error(error: KISAPIError) -> str:
    """KIS API 오류를 msg_cd/msg1 기준으로 대략적인 카테고리로 분류한다.

    운영 중 어떤 종류의 오류가 반복되는지 빠르게 파악하기 위한 용도이며,
    분류가 틀려도 자동매매 동작에는 영향을 주지 않는다 (관측성 목적).
    """
    msg_cd = (error.msg_cd or "").upper()
    msg1 = error.msg1 or ""
    msg1_lower = msg1.lower()

    if msg_cd in _TOKEN_MSG_CDS or any(kw in msg1 or kw in msg1_lower for kw in _TOKEN_KEYWORDS):
        return KIS_ERROR_TOKEN

    if msg_cd in _RATE_LIMIT_MSG_CDS or any(kw in msg1 or kw in msg1_lower for kw in _RATE_LIMIT_KEYWORDS):
        return KIS_ERROR_RATE_LIMIT

    if any(kw in msg1 for kw in _MARKET_CLOSED_KEYWORDS):
        return KIS_ERROR_MARKET_CLOSED

    if any(kw in msg1 for kw in _INSUFFICIENT_BALANCE_KEYWORDS):
        return KIS_ERROR_INSUFFICIENT_BALANCE

    return KIS_ERROR_UNKNOWN
