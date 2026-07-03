"""C-6.21: KIS 실시간 웹소켓 — 파서/집계기/구독 메시지 (오프라인 단위 테스트).

실연결 검증은 장중 수동 체크리스트 L절. 여기서는 프로토콜 처리의 순수 로직만 검증.
안전: 이 모듈은 시세 수신 전용 — 주문 TR이 없음을 상수로 확인한다.
"""
import json
from decimal import Decimal

from app.core.config import Settings
from app.trading.broker.kis_websocket import (
    MAX_WS_SYMBOLS,
    RealtimeCandleAggregator,
    Tick,
    build_subscribe_message,
    parse_ws_message,
)


def _tick_fields(symbol="005930", t="090015", price="70000", vol="120"):
    f = [""] * 15
    f[0], f[1], f[2], f[12] = symbol, t, price, vol
    return "^".join(f)


def test_parse_data_message_single_record():
    raw = f"0|H0STCNT0|001|{_tick_fields()}"
    kind, ticks = parse_ws_message(raw)
    assert kind == "ticks"
    assert len(ticks) == 1
    assert ticks[0].symbol_code == "005930"
    assert ticks[0].price == Decimal("70000")
    assert ticks[0].volume == 120


def test_parse_data_message_multi_record():
    raw = f"0|H0STCNT0|002|{_tick_fields(t='090015')}^{_tick_fields(t='090016', vol='30')}"
    kind, ticks = parse_ws_message(raw)
    assert kind == "ticks"
    assert len(ticks) == 2
    assert ticks[1].volume == 30


def test_parse_pingpong_and_garbage():
    kind, _ = parse_ws_message(json.dumps({"header": {"tr_id": "PINGPONG"}}))
    assert kind == "pingpong"
    assert parse_ws_message("")[0] == "unknown"
    assert parse_ws_message("0|OTHER|001|x")[0] == "unknown"
    assert parse_ws_message("not json not pipe")[0] == "unknown"


def test_subscribe_message_shape():
    msg = json.loads(build_subscribe_message("KEY", "005930"))
    assert msg["header"]["approval_key"] == "KEY"
    assert msg["header"]["tr_type"] == "1"
    assert msg["body"]["input"] == {"tr_id": "H0STCNT0", "tr_key": "005930"}
    # 주문 TR이 아님 — 시세 전용 상수 고정
    assert msg["body"]["input"]["tr_id"].startswith("H0")


def test_aggregator_builds_1m_ohlcv():
    agg = RealtimeCandleAggregator()
    for t, price, vol in (("090001", "100", 10), ("090030", "110", 5), ("090059", "105", 3)):
        agg.add(Tick("005930", t, Decimal(price), vol), "20260704")
    agg.add(Tick("005930", "090101", Decimal("106"), 7), "20260704")  # 다음 분

    done = agg.pop_completed(current_hhmm="0901")
    assert len(done) == 1
    symbol, c = done[0]
    assert symbol == "005930"
    assert c.trade_time == "090000"
    assert (c.open_price, c.high_price, c.low_price, c.close_price) == (
        Decimal("100"), Decimal("110"), Decimal("100"), Decimal("105"),
    )
    assert c.volume == 18
    assert agg.pending_count() == 1  # 0901 버킷은 진행 중


def test_aggregator_multi_symbol_separation():
    agg = RealtimeCandleAggregator()
    agg.add(Tick("005930", "090010", Decimal("100"), 1), "20260704")
    agg.add(Tick("000660", "090020", Decimal("200"), 2), "20260704")
    done = dict(agg.pop_completed("0902"))
    assert set(done) == {"005930", "000660"}


def test_ws_disabled_by_default():
    """안전 불변식: 새 백그라운드 수집은 코드 기본값에서 꺼져 있다."""
    s = Settings(_env_file=None)
    assert s.kis_ws_enabled is False
    assert MAX_WS_SYMBOLS == 40
