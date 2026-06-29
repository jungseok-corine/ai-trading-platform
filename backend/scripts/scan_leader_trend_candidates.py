"""Leader Trend 후보 스캐너 CLI (M2.15C-1) — **읽기 전용 · 주문/신호 없음**.

이미 적재된 `market_data` timeframe="1d"만 읽어 52주 지표/후보 A/B를 계산해 출력한다.
**DB write 없음 · 라이브 KIS 호출 없음 · SignalLog/Trade/Order 생성 없음 · 스케줄러/디스패처 없음 ·
execute 플래그 없음.** 후보 분류는 **매수 신호가 아니다**.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.db.session import async_session_factory
from app.services.leader_trend_scanner import LeaderTrendScanner

DEFAULT_SYMBOLS = ["005930", "000660", "035420", "005380", "051910"]


async def _run(args) -> int:
    symbols = [s.strip() for s in (args.symbols.split(",") if args.symbols else DEFAULT_SYMBOLS) if s.strip()]
    async with async_session_factory() as session:
        scanner = LeaderTrendScanner(session)  # read-only; provider/broker 미주입
        results = await scanner.scan(symbols)

    payload = {
        "note": "READ-ONLY scan. No orders, no signals, no trades, no DB writes. Candidates are NOT buy signals.",
        "symbols": symbols,
        "results": [m.to_dict() for m in results],
    }
    if args.json:
        print(json.dumps(payload, default=str, ensure_ascii=False))
    else:
        print(payload["note"])
        for m in results:
            print(
                f"{m.symbol} bucket={m.candidate_bucket} close={m.current_close} "
                f"gain%={m.low_52w_gain_pct} dd%={m.drawdown_from_52w_high_pct} "
                f"A={m.raw_candidate_a} B={m.raw_candidate_b} safe={m.operationally_safe_for_classification} "
                f"warn={m.data_quality_warnings}"
            )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Leader Trend candidate scanner (M2.15C-1). READ-ONLY. "
        "No orders/signals/trades/DB writes. Candidates are NOT buy signals."
    )
    p.add_argument("--symbols", default=None, help="comma-separated; default 5 pilot symbols")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
