"""KIS 실시간 웹소켓 시세 수집 (C-6.21, read-only).

실시간 체결가(H0STCNT0)를 구독해 틱을 1분봉으로 집계하고 market_data('1m')에
적재한다. **시세 수신 전용 — 주문/계좌 TR 없음.**

안전 경계:
- config `kis_ws_enabled=False` 기본 — 사람이 명시적으로 켠다 (새 백그라운드 표면 기본 off 규칙)
- 구독 상한 40종목 (KIS 세션당 41건 제한 보호)
- 연결 실패/끊김은 지수 백오프 재접속 — 실패가 앱을 중단시키지 않는다
- 프로토콜 파싱은 순수 함수로 분리해 오프라인 테스트 (실연결 검증은 장중 수동 체크리스트)
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.common.timezone import KST
from app.trading.broker.schemas import MinuteCandle

logger = logging.getLogger(__name__)

TR_REALTIME_PRICE = "H0STCNT0"  # 국내주식 실시간 체결가 (시세 전용)
MAX_WS_SYMBOLS = 40

# H0STCNT0 응답 필드 인덱스 (KIS 문서 기준 — 라이브 검증은 수동 체크리스트 L절)
_F_SYMBOL = 0        # MKSC_SHRN_ISCD
_F_TIME = 1          # STCK_CNTG_HOUR (HHMMSS)
_F_PRICE = 2         # STCK_PRPR
_F_VOLUME = 12       # CNTG_VOL (체결 거래량)
_MIN_FIELDS = 13


@dataclass
class Tick:
    symbol_code: str
    trade_time: str  # HHMMSS
    price: Decimal
    volume: int


def build_subscribe_message(approval_key: str, symbol_code: str, *, subscribe: bool = True) -> str:
    """H0STCNT0 구독/해지 메시지(JSON 문자열)를 만든다."""
    return json.dumps(
        {
            "header": {
                "approval_key": approval_key,
                "custtype": "P",
                "tr_type": "1" if subscribe else "2",
                "content-type": "utf-8",
            },
            "body": {"input": {"tr_id": TR_REALTIME_PRICE, "tr_key": symbol_code}},
        }
    )


def parse_ws_message(raw: str) -> tuple[str, list[Tick] | dict]:
    """수신 메시지를 (종류, 페이로드)로 파싱한다.

    - 데이터: "0|H0STCNT0|<건수>|<필드^...>" → ("ticks", [Tick...])
    - 제어(JSON): PINGPONG → ("pingpong", header) / 그 외 → ("control", body)
    - 알 수 없는 형식 → ("unknown", {})
    """
    if not raw:
        return "unknown", {}
    if raw[0] in ("0", "1") and "|" in raw:
        parts = raw.split("|", 3)
        if len(parts) < 4 or parts[1] != TR_REALTIME_PRICE:
            return "unknown", {}
        try:
            record_count = int(parts[2])
        except ValueError:
            record_count = 1
        fields = parts[3].split("^")
        per_record = len(fields) // max(record_count, 1)
        ticks: list[Tick] = []
        if per_record < _MIN_FIELDS:
            return "unknown", {}
        for i in range(record_count):
            rec = fields[i * per_record : (i + 1) * per_record]
            try:
                ticks.append(
                    Tick(
                        symbol_code=rec[_F_SYMBOL],
                        trade_time=rec[_F_TIME],
                        price=Decimal(rec[_F_PRICE]),
                        volume=int(rec[_F_VOLUME]),
                    )
                )
            except (IndexError, ValueError, InvalidOperation):
                continue
        return "ticks", ticks
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        return "unknown", {}
    header = msg.get("header") or {}
    if header.get("tr_id") == "PINGPONG":
        return "pingpong", header
    return "control", msg

class RealtimeCandleAggregator:
    """틱을 (종목, 분) 버킷의 1분봉으로 집계한다 (순수 — I/O 없음).

    pop_completed(): 현재 진행 중인 분 버킷을 제외한 완성 버킷을 꺼낸다.
    """

    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str], dict] = {}  # (symbol, HHMM) -> ohlcv

    def add(self, tick: Tick, business_date: str) -> None:
        if len(tick.trade_time) < 4:
            return
        key = (tick.symbol_code, tick.trade_time[:4])
        b = self._buckets.get(key)
        if b is None:
            self._buckets[key] = {
                "date": business_date,
                "open": tick.price, "high": tick.price,
                "low": tick.price, "close": tick.price, "volume": tick.volume,
            }
        else:
            b["high"] = max(b["high"], tick.price)
            b["low"] = min(b["low"], tick.price)
            b["close"] = tick.price
            b["volume"] += tick.volume

    def pop_completed(self, current_hhmm: str) -> list[tuple[str, MinuteCandle]]:
        """완성 버킷을 (symbol, candle) 목록으로 꺼낸다 (진행 중인 현재 분은 보류)."""
        done: list[tuple[str, MinuteCandle]] = []
        for key in sorted(self._buckets):
            symbol, hhmm = key
            if hhmm >= current_hhmm:
                continue  # 진행 중 버킷은 보류
            b = self._buckets.pop(key)
            done.append(
                (
                    symbol,
                    MinuteCandle(
                        business_date=b["date"], trade_time=f"{hhmm}00",
                        open_price=b["open"], high_price=b["high"],
                        low_price=b["low"], close_price=b["close"], volume=b["volume"],
                    ),
                )
            )
        return done

    def pending_count(self) -> int:
        return len(self._buckets)


class KISRealtimeCollector:
    """웹소켓 연결·구독·수신 루프. 완성 1분봉을 save_candles 콜백으로 넘긴다."""

    def __init__(
        self,
        *,
        ws_url: str,
        approval_key_provider,  # async () -> str
        symbols: list[str],
        on_candles,  # async (symbol, list[MinuteCandle]) -> None
        flush_seconds: float = 5.0,
    ) -> None:
        self._ws_url = ws_url
        self._approval_key_provider = approval_key_provider
        self._symbols = symbols[:MAX_WS_SYMBOLS]
        self._on_candles = on_candles
        self._flush_seconds = flush_seconds
        self._aggregator = RealtimeCandleAggregator()
        self._stopped = asyncio.Event()
        self.ticks_received = 0
        self.candles_flushed = 0
        self.last_error: str | None = None

    def stop(self) -> None:
        self._stopped.set()

    async def run_forever(self) -> None:
        """연결 유지 루프 — 끊기면 지수 백오프로 재접속한다."""
        import websockets  # noqa: PLC0415

        backoff = 1.0
        while not self._stopped.is_set():
            try:
                approval_key = await self._approval_key_provider()
                async with websockets.connect(self._ws_url, ping_interval=None) as ws:
                    for symbol in self._symbols:
                        await ws.send(build_subscribe_message(approval_key, symbol))
                    logger.info("KIS WS 연결 — %d종목 구독", len(self._symbols))
                    backoff = 1.0
                    await self._recv_loop(ws)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - 수집 실패가 앱을 중단시키지 않도록
                self.last_error = str(exc) or type(exc).__name__
                logger.warning("KIS WS 오류 — %.0fs 후 재접속: %s", backoff, self.last_error)
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, 60.0)

    async def _recv_loop(self, ws) -> None:
        last_flush = asyncio.get_event_loop().time()
        while not self._stopped.is_set():
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=self._flush_seconds)
            except asyncio.TimeoutError:
                raw = None
            if raw is not None:
                kind, payload = parse_ws_message(
                    raw if isinstance(raw, str) else raw.decode("utf-8", "ignore")
                )
                if kind == "ticks":
                    today = datetime.now(KST).strftime("%Y%m%d")
                    for tick in payload:
                        self._aggregator.add(tick, today)
                        self.ticks_received += 1
                elif kind == "pingpong":
                    await ws.send(raw)  # 에코 응답 (연결 유지)

            now = asyncio.get_event_loop().time()
            if now - last_flush >= self._flush_seconds:
                await self._flush()
                last_flush = now
        await self._flush()

    async def _flush(self) -> None:
        current_hhmm = datetime.now(KST).strftime("%H%M")
        pairs = self._aggregator.pop_completed(current_hhmm)
        if not pairs:
            return
        by_symbol: dict[str, list[MinuteCandle]] = {}
        for symbol, candle in pairs:
            by_symbol.setdefault(symbol, []).append(candle)
        for symbol, candles in by_symbol.items():
            try:
                await self._on_candles(symbol, candles)
                self.candles_flushed += len(candles)
            except Exception as exc:  # noqa: BLE001 - 저장 실패가 수집을 중단시키지 않도록
                logger.warning("WS 1분봉 저장 실패 (%s): %s", symbol, exc)


async def fetch_approval_key(http_client, base_url: str, app_key: str, app_secret: str) -> str:
    """웹소켓 접속키(approval_key) 발급 — REST 토큰과 별개의 시세 전용 키."""
    response = await http_client.post(
        f"{base_url.rstrip('/')}/oauth2/Approval",
        json={"grant_type": "client_credentials", "appkey": app_key, "secretkey": app_secret},
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    response.raise_for_status()
    key = response.json().get("approval_key")
    if not key:
        raise RuntimeError("approval_key 발급 실패 — 응답에 키 없음")
    return key
