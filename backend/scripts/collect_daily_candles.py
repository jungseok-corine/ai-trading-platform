"""Daily candle collector CLI (M2.15B-2) — dry-run 기본 · read-only 시세 수집.

기본 **dry-run**(무쓰기·무 KIS 호출). 실제 수집(execute)에는 `--execute` + `--confirm-daily-candle-collection`
둘 다 + hard guard 통과가 필요하다. **주문/거래 무관 · SignalLog/Trade/Order 미생성 · 스케줄러 없음.**
`--coverage-only`는 DB 읽기 전용. (M2.15B-2 단계에서는 dev DB 대상 execute를 실행하지 않는다.)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.services.market_data_daily_collector import MarketDataDailyCollector

PRODUCTION_ENV_HINTS = ("prod", "production", "live")


def evaluate_guards(settings, *, confirm: bool, execute: bool) -> list[str]:
    """execute 전 hard guard. 거부 사유 리스트(빈 리스트=통과). 순수 함수."""
    reasons: list[str] = []
    app_env = str(getattr(settings, "app_env", "") or "")
    if any(h in app_env.lower() for h in PRODUCTION_ENV_HINTS):
        reasons.append(f"APP_ENV={app_env!r} looks like production")
    if not confirm:
        reasons.append("missing --confirm-daily-candle-collection")
    if not execute:
        reasons.append("missing --execute (default is dry-run)")
    if getattr(settings, "kis_real_trading_enabled", False):
        reasons.append("KIS_REAL_TRADING_ENABLED is true")
    if getattr(settings, "paper_signal_session_runner_enabled", False):
        reasons.append("paper_signal_session_runner_enabled is true")
    if getattr(settings, "paper_signal_recurring_plan_dispatcher_enabled", False):
        reasons.append("paper_signal_recurring_plan_dispatcher_enabled is true")
    db_url = str(getattr(settings, "database_url", "") or "")
    if not any(tok in db_url for tok in ("localhost", "127.0.0.1", "_test", "/trading_platform")):
        reasons.append("database_url does not look local/dev/test")
    return reasons


def _build_daily_provider(settings):
    """execute 전용: read-only 일봉 조회 KIS 클라이언트. 주문 경로 미사용."""
    import httpx

    from app.trading.broker.kis_paper import KISPaperBrokerClient

    http = httpx.AsyncClient(timeout=10.0)
    client = KISPaperBrokerClient(
        base_url=settings.kis_paper_base_url, app_key=settings.kis_app_key,
        app_secret=settings.kis_app_secret, account_no=settings.kis_account_no,
        market_div_code=settings.kr_market_div_code, http_client=http,
        token_cache_path=settings.kis_token_cache_path,
        rate_limit_min_interval_seconds=settings.kis_rate_limit_min_interval_seconds,
        rate_limit_cooldown_seconds=settings.kis_rate_limit_cooldown_seconds,
        request_max_retries=settings.kis_request_max_retries,
        request_retry_base_delay_seconds=settings.kis_request_retry_base_delay_seconds,
        request_retry_max_delay_seconds=settings.kis_request_retry_max_delay_seconds,
    )
    return client, http


async def _run(args) -> int:
    settings = get_settings()
    symbols_arg = [s for s in (args.symbols.split(",") if args.symbols else []) if s.strip()]

    async with async_session_factory() as session:
        collector = MarketDataDailyCollector(session)
        universe = await collector.build_pilot_universe(
            symbols=symbols_arg or None, limit=args.limit, from_watchlist=args.from_watchlist
        )

        if args.coverage_only:
            result = await collector.coverage_report(symbols=universe or None)
            print(json.dumps(result, default=str, ensure_ascii=False) if args.json else result)
            return 0

        if not args.execute:
            plan = collector.dry_run_plan(universe, args.count)
            print(json.dumps(plan.to_dict(), default=str, ensure_ascii=False) if args.json
                  else plan.to_dict())
            return 0

        reasons = evaluate_guards(settings, confirm=args.confirm, execute=args.execute)
        if reasons:
            print("REFUSED (hard guards):")
            for r in reasons:
                print(f"  - {r}")
            return 2

        # execute: read-only KIS 일봉 provider 주입 후 멱등 수집.
        client, http = _build_daily_provider(settings)
        try:
            exec_collector = MarketDataDailyCollector(session, daily_provider=client)
            report = await exec_collector.collect(
                universe, count=args.count, execute=True, overwrite=args.overwrite
            )
            await session.commit()
        finally:
            await http.aclose()
        print(json.dumps(report.to_dict(), default=str, ensure_ascii=False) if args.json
              else report.to_dict())
        return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Daily candle collector (M2.15B-2). dry-run default. read-only market data.")
    p.add_argument("--symbols", default=None, help="comma-separated, e.g. 005930,000660")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--count", type=int, default=252)
    p.add_argument("--from-watchlist", action="store_true", dest="from_watchlist")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--confirm-daily-candle-collection", action="store_true", dest="confirm")
    p.add_argument("--coverage-only", action="store_true", dest="coverage_only")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
