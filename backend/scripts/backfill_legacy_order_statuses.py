"""C-2.15: Legacy cancelled order 상태 backfill — dry-run 전용.

이전 버전에서 pending stale 처리 후 실제 체결 기록이 있는데
DB에 cancelled로 남아 있을 가능성이 있는 주문을 조사한다.

기능:
  - DB에서 cancelled/stale_cancelled 주문 조회
  - KIS 일별주문체결조회(VTTC0081R/TTTC0081R)로 broker_order_id 조회
  - 실제 체결 기록이 있으면 dry-run 결과로 표시
  - 기본은 dry-run만 — --apply 없이는 DB 수정 금지
  - real mode apply는 금지 (read-only 정책 유지)

주문 API 호출 금지:
  - 이 스크립트는 어떤 경우에도 place_order를 호출하지 않는다.
  - 조회만 수행한다 (VTTC0081R, TTTC0081R).

사용법:
    # dry-run (기본)
    .venv/bin/python scripts/backfill_legacy_order_statuses.py

    # paper 계좌 apply (DB 수정)
    .venv/bin/python scripts/backfill_legacy_order_statuses.py --apply --paper-only

    # 특정 account_id만 조사
    .venv/bin/python scripts/backfill_legacy_order_statuses.py --account-id 1
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

_ENV_FILE = _BACKEND_DIR / ".env"
if _ENV_FILE.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_ENV_FILE, override=False)

_KST = ZoneInfo("Asia/Seoul")


@dataclass
class BackfillOrderResult:
    trade_id: int
    account_id: int
    account_type: str
    symbol_code: str
    broker_order_id: str | None
    current_status: str
    entry_time: datetime | None
    found_in_broker: bool = False
    broker_filled_qty: int | None = None
    broker_filled_price: float | None = None
    would_update_to: str | None = None
    skip_reason: str | None = None


@dataclass
class BackfillReport:
    checked_orders: int = 0
    matched_filled_orders: list[BackfillOrderResult] = field(default_factory=list)
    would_update_to_filled: int = 0
    would_create_trades: int = 0
    unmatched_orders: list[BackfillOrderResult] = field(default_factory=list)
    skipped_orders: list[BackfillOrderResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    order_api_called: bool = False  # 항상 False


async def _fetch_cancelled_orders(session, account_id: int | None) -> list:
    """DB에서 cancelled 상태 주문을 조회한다."""
    from sqlalchemy import select
    from app.domain.models.enums import OrderStatus
    from app.domain.models.trade import Trade

    stmt = select(Trade).where(Trade.order_status == OrderStatus.CANCELLED)
    if account_id is not None:
        stmt = stmt.where(Trade.account_id == account_id)
    stmt = stmt.order_by(Trade.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _check_broker_execution(broker, broker_order_id: str, date_from: date, date_to: date) -> dict | None:
    """VTTC0081R/TTTC0081R로 broker_order_id에 해당하는 체결 기록을 조회한다.

    place_order는 절대 호출하지 않는다.
    """
    try:
        executions = await broker.get_daily_executions(
            start_date=date_from.strftime("%Y%m%d"),
            end_date=date_to.strftime("%Y%m%d"),
        )
        for ex in executions:
            if ex.order_id == broker_order_id or ex.order_id.strip() == broker_order_id.strip():
                return {
                    "order_id": ex.order_id,
                    "filled_quantity": ex.filled_quantity,
                    "total_quantity": ex.total_quantity,
                    "filled_price": ex.filled_price,
                    "cancelled": ex.cancelled,
                }
    except Exception as e:
        return {"error": str(e)}
    return None


async def _run_backfill(
    account_id: int | None,
    apply: bool,
    paper_only: bool,
) -> BackfillReport:
    import httpx
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import get_settings
    from app.domain.models.account import Account
    from app.domain.models.enums import AccountType, OrderStatus
    from app.domain.models.trade import Trade

    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    report = BackfillReport()

    try:
        async with factory() as session:
            trades = await _fetch_cancelled_orders(session, account_id)
            report.checked_orders = len(trades)

            if not trades:
                return report

            # account_id별로 그룹화
            account_ids = list({t.account_id for t in trades})

            # account type 조회
            from sqlalchemy import select
            acc_result = await session.execute(
                select(Account).where(Account.id.in_(account_ids))
            )
            accounts = {a.id: a for a in acc_result.scalars().all()}

            for trade in trades:
                acc = accounts.get(trade.account_id)
                if acc is None:
                    report.warnings.append(f"trade_id={trade.id}: account_id={trade.account_id} not found")
                    continue

                result = BackfillOrderResult(
                    trade_id=trade.id,
                    account_id=trade.account_id,
                    account_type=acc.account_type.value,
                    symbol_code=trade.symbol_code,
                    broker_order_id=trade.broker_order_id,
                    current_status=trade.order_status.value,
                    entry_time=trade.entry_time,
                )

                if acc.account_type == AccountType.LIVE:
                    result.skip_reason = "real account — KIS API 조회 건너뜀 (read-only 정책)"
                    report.skipped_orders.append(result)
                    continue

                if paper_only and acc.account_type != AccountType.PAPER:
                    result.skip_reason = "--paper-only: non-paper account skipped"
                    report.skipped_orders.append(result)
                    continue

                if not trade.broker_order_id:
                    result.skip_reason = "broker_order_id 없음"
                    report.skipped_orders.append(result)
                    continue

                # KIS paper broker로 조회
                # broker_account_no 없을 경우 skip
                if not acc.broker_account_no:
                    result.skip_reason = "broker_account_no 없음"
                    report.skipped_orders.append(result)
                    continue

                date_ref = trade.entry_time.date() if trade.entry_time else datetime.now(_KST).date()
                date_from = date_ref - timedelta(days=1)
                date_to = date_ref + timedelta(days=1)

                app_key = os.environ.get("KIS_APP_KEY", "")
                app_secret = os.environ.get("KIS_APP_SECRET", "")
                base_url = os.environ.get("KIS_BASE_URL", "https://openapivts.koreainvestment.com:29443")
                token_cache = os.environ.get("KIS_TOKEN_CACHE_PATH", ".cache/kis_token.json")

                if not (app_key and app_secret):
                    result.skip_reason = "KIS_APP_KEY/KIS_APP_SECRET 미설정"
                    report.skipped_orders.append(result)
                    report.warnings.append("KIS_APP_KEY 또는 KIS_APP_SECRET 환경변수가 설정되지 않아 KIS API 조회를 건너뜁니다.")
                    continue

                try:
                    async with httpx.AsyncClient(timeout=30.0) as http:
                        from app.trading.broker.kis_paper import KISPaperBrokerClient
                        broker = KISPaperBrokerClient(
                            base_url=base_url,
                            app_key=app_key,
                            app_secret=app_secret,
                            account_no=acc.broker_account_no,
                            http_client=http,
                            token_cache_path=token_cache,
                        )
                        broker_data = await _check_broker_execution(
                            broker, trade.broker_order_id, date_from, date_to
                        )
                except Exception as e:
                    result.skip_reason = f"KIS API 오류: {e}"
                    report.skipped_orders.append(result)
                    report.warnings.append(f"trade_id={trade.id} KIS API 오류: {e}")
                    continue

                if broker_data is None:
                    result.found_in_broker = False
                    report.unmatched_orders.append(result)
                    continue

                if "error" in broker_data:
                    result.skip_reason = f"KIS 응답 오류: {broker_data['error']}"
                    report.skipped_orders.append(result)
                    report.warnings.append(f"trade_id={trade.id} KIS 응답 오류: {broker_data['error']}")
                    continue

                result.found_in_broker = True
                result.broker_filled_qty = broker_data.get("filled_quantity")
                result.broker_filled_price = broker_data.get("filled_price")

                is_filled = (
                    broker_data.get("filled_quantity", 0) > 0
                    and not broker_data.get("cancelled", True)
                )

                if is_filled:
                    result.would_update_to = "filled"
                    report.would_update_to_filled += 1

                    if apply and acc.account_type == AccountType.PAPER:
                        trade.order_status = OrderStatus.FILLED
                        if broker_data.get("filled_price"):
                            trade.entry_price = broker_data["filled_price"]
                        await session.flush()
                        result.would_update_to = "filled (APPLIED)"
                    elif apply and acc.account_type != AccountType.PAPER:
                        result.would_update_to = "filled (skipped: real account apply forbidden)"
                        report.warnings.append(
                            f"trade_id={trade.id}: real account DB apply is forbidden. "
                            "Use paper_only or apply manually."
                        )

                    report.matched_filled_orders.append(result)
                else:
                    result.would_update_to = None
                    report.unmatched_orders.append(result)

            if apply:
                await session.commit()

    finally:
        await engine.dispose()

    return report


def _print_report(report: BackfillReport, apply: bool) -> None:
    mode = "APPLY (PAPER ONLY)" if apply else "DRY-RUN"
    print(f"""
{'=' * 60}
  Legacy Order Status Backfill — C-2.15 ({mode})
{'=' * 60}
  checked_orders          : {report.checked_orders}
  matched_filled_orders   : {len(report.matched_filled_orders)}
  would_update_to_filled  : {report.would_update_to_filled}
  unmatched_orders        : {len(report.unmatched_orders)}
  skipped_orders          : {len(report.skipped_orders)}
  order_api_called        : {report.order_api_called}  ← 항상 False
""")

    if report.matched_filled_orders:
        print("  [매칭된 체결 주문 (DB에 cancelled, KIS에 filled)]")
        for r in report.matched_filled_orders:
            print(f"    trade_id={r.trade_id} acc={r.account_id}({r.account_type}) "
                  f"symbol={r.symbol_code} broker_order={r.broker_order_id} "
                  f"filled_qty={r.broker_filled_qty} filled_price={r.broker_filled_price} "
                  f"→ {r.would_update_to}")
        print()

    if report.unmatched_orders:
        print(f"  [미매칭 주문 (KIS에서 체결 기록 없음): {len(report.unmatched_orders)}건]")
        for r in report.unmatched_orders[:10]:
            print(f"    trade_id={r.trade_id} acc={r.account_id} symbol={r.symbol_code} "
                  f"broker_order={r.broker_order_id} found_in_broker={r.found_in_broker}")
        if len(report.unmatched_orders) > 10:
            print(f"    ... (이하 {len(report.unmatched_orders) - 10}건 생략)")
        print()

    if report.skipped_orders:
        print(f"  [건너뛴 주문: {len(report.skipped_orders)}건]")
        for r in report.skipped_orders[:5]:
            print(f"    trade_id={r.trade_id} reason={r.skip_reason}")
        if len(report.skipped_orders) > 5:
            print(f"    ... (이하 {len(report.skipped_orders) - 5}건 생략)")
        print()

    if report.warnings:
        print(f"  [경고: {len(report.warnings)}건]")
        for w in report.warnings:
            print(f"    - {w}")
        print()

    if not apply:
        print("  [DRY-RUN] DB 수정 없음. --apply --paper-only 로 실제 적용 가능.")
        print("  [주의] real 계좌 주문은 --apply 시에도 DB 수정하지 않습니다.")

    print(f"{'=' * 60}")


def main() -> None:
    parser = argparse.ArgumentParser(description="C-2.15: Legacy cancelled order backfill")
    parser.add_argument("--account-id", type=int, default=None)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="paper 계좌 주문만 DB 수정 적용 (real 계좌는 항상 read-only)",
    )
    parser.add_argument(
        "--paper-only",
        action="store_true",
        help="paper 계좌만 조회",
    )
    args = parser.parse_args()

    if args.apply and not args.paper_only:
        print("\n[WARNING] --apply 시에는 --paper-only를 함께 지정하는 것을 권장합니다.")
        print("  real 계좌 주문은 apply 시에도 변경되지 않습니다.\n")

    report = asyncio.run(_run_backfill(
        account_id=args.account_id,
        apply=args.apply,
        paper_only=args.paper_only,
    ))
    _print_report(report, args.apply)

    if report.warnings:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
