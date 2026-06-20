"""매매 테이프(Trade Tape) 빌더 — LLM 분석 입력용 압축 표현 (C-2.52).

원칙:
  1. 원본은 절대 버리지 않는다(이 모듈은 읽기 전용 변환만; market_data/trades는 DB에 그대로).
  2. 압축은 매매 구간만 1분 상세, 나머지는 coarse 집계로 토큰을 줄인다.
  3. **압축이 중요한 데이터를 조용히 떨어뜨리지 않도록**, 매매 구간 밖이라도 큰 변동/
     거래량 급증(notable events)은 항상 감지해 포함하고, 무엇을 넣고 뺐는지 audit에 남긴다.
  4. 분석에 쓸 수치(VWAP 대비, 당일 레인지 위치, 거래량 z-score, MFE/MAE)는 여기서
     미리 계산해 넘긴다 — LLM이 캔들에서 직접 산수하지 않게 해 토큰·오류를 줄인다.

순수 함수 모듈(네트워크/DB 없음) — 테스트가 쉽다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import mean, pstdev


@dataclass
class Candle:
    ts: datetime
    o: float
    h: float
    lo: float
    c: float
    v: float


@dataclass
class TradeEvent:
    side: str  # "buy" | "sell"
    quantity: int
    entry_time: datetime | None = None
    exit_time: datetime | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    pnl_amount: float | None = None
    pnl_pct: float | None = None

    @property
    def status(self) -> str:
        """청산가/청산시각이 없으면 'open'(미청산 단건 주문), 있으면 'closed'."""
        return "closed" if self.exit_time is not None else "open"

    def to_dict(self) -> dict:
        return {
            "side": self.side,
            "quantity": self.quantity,
            "status": self.status,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "pnl_amount": self.pnl_amount,
            "pnl_pct": self.pnl_pct,
        }


def _typical(c: Candle) -> float:
    return (c.h + c.lo + c.c) / 3


def vwap(candles: list[Candle]) -> float | None:
    total_vol = sum(c.v for c in candles)
    if total_vol <= 0:
        return None
    return round(sum(_typical(c) * c.v for c in candles) / total_vol, 4)


def day_summary(candles: list[Candle]) -> dict | None:
    if not candles:
        return None
    hi = max(c.h for c in candles)
    lo = min(c.lo for c in candles)
    return {
        "open": candles[0].o,
        "high": hi,
        "low": lo,
        "close": candles[-1].c,
        "vwap": vwap(candles),
        "volume": sum(c.v for c in candles),
        "range_pct": round((hi - lo) / lo * 100, 4) if lo else None,
        "candle_count": len(candles),
    }


def range_percentile(price: float | None, lo: float | None, hi: float | None) -> float | None:
    """price가 당일 레인지(lo~hi)에서 차지하는 위치(0=저가, 100=고가)."""
    if price is None or hi is None or lo is None or hi == lo:
        return None
    return round((price - lo) / (hi - lo) * 100, 1)


def volume_zscore(candles: list[Candle], idx: int) -> float | None:
    vols = [c.v for c in candles]
    if len(vols) < 2:
        return None
    s = pstdev(vols)
    if s == 0:
        return None
    return round((vols[idx] - mean(vols)) / s, 2)


def candle_index_at(candles: list[Candle], ts: datetime) -> int | None:
    """ts 시점의(또는 직전) 캔들 인덱스. 없으면 None."""
    idx: int | None = None
    for i, c in enumerate(candles):
        if c.ts <= ts:
            idx = i
        else:
            break
    return idx


def mfe_mae(
    candles: list[Candle], entry_idx: int | None, end_idx: int | None,
    entry_price: float | None, side: str,
) -> tuple[float | None, float | None]:
    """진입 후 최대 유리/불리 변동(%). end_idx 없으면 당일 끝까지."""
    if entry_price in (None, 0) or entry_idx is None:
        return (None, None)
    seg = candles[entry_idx: (end_idx + 1) if end_idx is not None else len(candles)]
    if not seg:
        return (None, None)
    if side == "sell":  # 숏 관점
        mfe = max((entry_price - c.lo) / entry_price * 100 for c in seg)
        mae = min((entry_price - c.h) / entry_price * 100 for c in seg)
    else:  # 롱(buy)
        mfe = max((c.h - entry_price) / entry_price * 100 for c in seg)
        mae = min((c.lo - entry_price) / entry_price * 100 for c in seg)
    return (round(mfe, 4), round(mae, 4))


def trade_features(candles: list[Candle], trade: TradeEvent) -> dict:
    """LLM이 직접 계산하지 않도록 매매 품질 지표를 사전계산한다."""
    summ = day_summary(candles)
    feats: dict = {"realized_return_pct": trade.pnl_pct}
    if summ and trade.entry_price is not None:
        v = summ["vwap"]
        feats["entry_vs_vwap_pct"] = (
            round((trade.entry_price - v) / v * 100, 4) if v else None
        )
        feats["entry_range_percentile"] = range_percentile(
            trade.entry_price, summ["low"], summ["high"]
        )
    e_idx = candle_index_at(candles, trade.entry_time) if trade.entry_time else None
    x_idx = candle_index_at(candles, trade.exit_time) if trade.exit_time else None
    feats["status"] = trade.status
    if e_idx is not None:
        feats["entry_volume_zscore"] = volume_zscore(candles, e_idx)
        mfe, mae = mfe_mae(candles, e_idx, x_idx, trade.entry_price, trade.side)
        feats["mfe_pct"] = mfe
        feats["mae_pct"] = mae
        # MFE/MAE 기준 구간: 청산까지(closed) vs 장 마감까지(open=미청산이라 미실현).
        feats["excursion_basis"] = "to_exit" if x_idx is not None else "to_session_close"
    return feats


def detect_notable(candles: list[Candle], ret_k: float = 3.0, vol_m: float = 3.0) -> list[dict]:
    """매매 구간 밖이라도 '큰 1분 변동' 또는 '거래량 급증'을 감지한다.

    압축이 중요한 사건을 조용히 버리지 않게 하는 가드. 표준편차의 ret_k배 초과 변동 또는
    평균 거래량의 vol_m배 초과를 notable로 본다.
    """
    if len(candles) < 3:
        return []
    rets = [
        (candles[i].c - candles[i - 1].c) / candles[i - 1].c * 100
        if candles[i - 1].c else 0.0
        for i in range(1, len(candles))
    ]
    s = pstdev(rets) if len(rets) > 1 else 0.0
    avg_vol = mean(c.v for c in candles)
    notable: list[dict] = []
    for i, c in enumerate(candles):
        ret = rets[i - 1] if i > 0 else 0.0
        reasons = []
        if s > 0 and abs(ret) > ret_k * s:
            reasons.append("big_move")
        if avg_vol > 0 and c.v > vol_m * avg_vol:
            reasons.append("volume_spike")
        if reasons:
            notable.append({
                "index": i, "ts": c.ts.isoformat(), "close": c.c,
                "return_pct": round(ret, 4), "volume": c.v, "reasons": reasons,
            })
    return notable


def _aggregate(chunk: list[Candle]) -> dict:
    return {
        "ts_start": chunk[0].ts.isoformat(),
        "ts_end": chunk[-1].ts.isoformat(),
        "o": chunk[0].o,
        "h": max(c.h for c in chunk),
        "l": min(c.lo for c in chunk),
        "c": chunk[-1].c,
        "v": sum(c.v for c in chunk),
        "n": len(chunk),
    }


def build_trade_tape(
    candles: list[Candle],
    trades: list[TradeEvent],
    *,
    window: int = 15,
    coarse: int = 15,
) -> dict:
    """매매 테이프 번들을 만든다. 매매±window 분과 notable 캔들은 1분 상세,
    나머지는 coarse개 단위로 집계한다. audit에 압축 통계를 남긴다.
    """
    summary = day_summary(candles)
    notable = detect_notable(candles)

    # 상세로 유지할 인덱스: 매매 진입/청산 ±window + notable
    keep: set[int] = {n["index"] for n in notable}
    for t in trades:
        for ts in (t.entry_time, t.exit_time):
            if ts is None:
                continue
            idx = candle_index_at(candles, ts)
            if idx is not None:
                for j in range(max(0, idx - window), min(len(candles), idx + window + 1)):
                    keep.add(j)

    detailed: list[dict] = []
    coarse_buckets: list[dict] = []
    chunk: list[Candle] = []
    for i, c in enumerate(candles):
        if i in keep:
            if chunk:
                coarse_buckets.append(_aggregate(chunk))
                chunk = []
            detailed.append({"ts": c.ts.isoformat(), "o": c.o, "h": c.h, "l": c.lo, "c": c.c, "v": c.v})
        else:
            chunk.append(c)
            if len(chunk) >= coarse:
                coarse_buckets.append(_aggregate(chunk))
                chunk = []
    if chunk:
        coarse_buckets.append(_aggregate(chunk))

    return {
        "day_summary": summary,
        "trades": [
            {**t.to_dict(), "features": trade_features(candles, t)} for t in trades
        ],
        "notable_events": [{k: v for k, v in n.items() if k != "index"} for n in notable],
        "detailed_candles": detailed,
        "coarse_candles": coarse_buckets,
        "audit": {
            "candles_total": len(candles),
            "candles_detailed": len(detailed),
            "candles_aggregated": sum(b["n"] for b in coarse_buckets),
            "coarse_buckets": len(coarse_buckets),
            "notable_events": len(notable),
            "note": "원본 분봉/체결은 DB에 보존됨. 본 번들은 LLM 입력용 압축본.",
        },
    }
