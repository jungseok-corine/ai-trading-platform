from app.trading.broker.order_id import normalize_order_id


def test_normalize_order_id_strips_leading_zeros() -> None:
    assert normalize_order_id("0000123456") == "123456"


def test_normalize_order_id_strips_whitespace() -> None:
    assert normalize_order_id("  0000123456  ") == "123456"


def test_normalize_order_id_handles_int_input() -> None:
    assert normalize_order_id(123456) == "123456"


def test_normalize_order_id_matches_padded_and_unpadded() -> None:
    assert normalize_order_id("0000123456") == normalize_order_id("123456")


def test_normalize_order_id_all_zeros_returns_zero() -> None:
    assert normalize_order_id("0000000000") == "0"


def test_normalize_order_id_none_returns_empty_string() -> None:
    assert normalize_order_id(None) == ""
