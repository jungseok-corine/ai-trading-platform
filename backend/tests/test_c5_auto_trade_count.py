"""C-5.22: 대시보드/안전 점검의 자동매매 카운트가 유니버스 자동매매도 포함하는지."""
from app.trading.strategy.schemas import params_auto_trades


def test_single_symbol_auto_trade() -> None:
    assert params_auto_trades({"symbol_code": "005930", "auto_trade_enabled": True}) is True
    assert params_auto_trades({"symbol_code": "005930", "auto_trade_enabled": False}) is False


def test_universe_uses_universe_auto_trade_flag() -> None:
    # 유니버스 모드는 단일종목용 auto_trade_enabled가 아니라 universe_auto_trade를 본다.
    assert params_auto_trades(
        {"universe": "watchlist", "universe_auto_trade": True, "account_id": 1}
    ) is True
    assert params_auto_trades(
        {"universe": "watchlist", "universe_auto_trade": False}
    ) is False
    # 유니버스에 (잘못) auto_trade_enabled만 켜져 있어도 자동매매로 세지 않는다.
    assert params_auto_trades(
        {"universe": "watchlist", "auto_trade_enabled": True}
    ) is False


def test_empty_or_none() -> None:
    assert params_auto_trades(None) is False
    assert params_auto_trades({}) is False
