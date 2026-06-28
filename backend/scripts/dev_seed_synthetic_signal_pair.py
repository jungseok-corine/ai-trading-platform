"""Dev-only SYNTHETIC baseline/challenger signal pair bootstrap (M2.14L).

빈 dev/test DB에서 **수동 tick UI 흐름을 시연**할 최소 레코드를 만든다(설계: M2.14K).
**이 데이터는 거래 증거가 아니다(SYNTHETIC/DEMO/DEV_ONLY).** 전략 수익성 판단·M2.14B-3d 정당화·실 성과
export에 쓰면 안 된다.

만들 수 있는 것: Strategy ×1 · StrategyVersion ×2(DRAFT) · PaperSignalSession ×2(active) ·
PaperSignalRecurringRun ×1(prepared, 서비스 경유). **만들지 않는 것: SignalLog · Trade · Order · 스케줄러 잡 ·
디스패처 활성 · broker/KIS 호출.** tick은 수행하지 않는다(운영자가 UI/M2.14H로 수동).

기본 dry-run(읽기 전용·계획만 출력). 쓰기에는 `--confirm-dev-synthetic-bootstrap` + `--execute` 둘 다 필요하고,
hard guard(아래)를 모두 통과해야 한다. cleanup은 M2.14L에서 의도적으로 미구현 — 미래 cleanup은 라벨된
SYNTHETIC/DEMO만 대상으로 하며 reset/purge는 없다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.paper_signal_session import PaperSignalSession
from app.domain.models.strategy import Strategy, StrategyVersion
from app.services.paper_signal_recurring_run_service import PaperSignalRecurringRunService

# 모든 합성 레코드에 박는 라벨(검색/식별/오인 방지).
SYNTHETIC_LABELS = [
    "SYNTHETIC",
    "DEMO",
    "NOT_TRADING_EVIDENCE",
    "NOT_REAL_PERFORMANCE",
    "DEV_ONLY",
]
LABEL_TAG = "[" + "][".join(SYNTHETIC_LABELS) + "]"  # [SYNTHETIC][DEMO]...[DEV_ONLY]
STARTED_BY = "dev_synthetic_bootstrap"
STRATEGY_NAME = f"SYNTHETIC DEMO signal pair {LABEL_TAG}"
NOTE = f"{LABEL_TAG} dev-only synthetic pair — not trading evidence (M2.14L)."
PRODUCTION_ENV_HINTS = ("prod", "production", "live")


def evaluate_guards(settings, *, confirm: bool, execute: bool) -> list[str]:
    """쓰기 전에 평가하는 hard guard. 거부 사유 리스트를 반환(빈 리스트 = 통과). 순수 함수(테스트 용이)."""
    reasons: list[str] = []
    app_env = str(getattr(settings, "app_env", "") or "")
    if any(h in app_env.lower() for h in PRODUCTION_ENV_HINTS):
        reasons.append(f"APP_ENV={app_env!r} looks like production")
    if not confirm:
        reasons.append("missing --confirm-dev-synthetic-bootstrap")
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


def _version_params(symbol: str) -> dict:
    return {
        "strategy_type": "moving_average_cross",
        "symbol_code": symbol,
        "auto_trade_enabled": False,
        "_synthetic": True,
        "_demo": True,
        "_not_trading_evidence": True,
        "_dev_only": True,
    }


async def find_existing_pair(session, symbol: str) -> dict | None:
    """라벨/started_by/symbol로 기존 SYNTHETIC challenger 세션을 찾고 페어/계획을 역추적(읽기 전용)."""
    chal = (
        await session.execute(
            select(PaperSignalSession).where(
                PaperSignalSession.started_by == STARTED_BY,
                PaperSignalSession.source_type == "signal_challenger",
                PaperSignalSession.symbol_code == symbol,
                PaperSignalSession.status == "active",
            ).order_by(PaperSignalSession.id.asc())
        )
    ).scalars().first()
    if chal is None:
        return None
    repo = PaperSignalRecurringRunService(session)._repo
    plan = await repo.find_open_for_pair(chal.baseline_session_id, chal.id)
    return {
        "baseline_session_id": chal.baseline_session_id,
        "challenger_session_id": chal.id,
        "challenger_version_id": chal.strategy_version_id,
        "recurring_plan_id": (plan.id if plan else None),
        "reused": True,
    }


async def seed_synthetic_pair(
    session, *, symbol: str, interval_seconds: int, max_runs: int, force_new: bool = False
) -> dict:
    """SYNTHETIC 페어 + prepared 계획을 find-or-create 한다(commit은 호출자/서비스가 수행).

    SignalLog/Trade/Order/broker 미사용. recurring 계획은 서비스 create_prepared_pair_plan 경유(검증 재사용).
    """
    if not force_new:
        existing = await find_existing_pair(session, symbol)
        if existing is not None:
            return existing

    strat = Strategy(name=STRATEGY_NAME, description=NOTE)
    session.add(strat)
    await session.flush()
    b_ver = StrategyVersion(
        strategy_id=strat.id, version_no=1, status=StrategyVersionStatus.DRAFT,
        parameters=_version_params(symbol), change_description=NOTE,
    )
    c_ver = StrategyVersion(
        strategy_id=strat.id, version_no=2, status=StrategyVersionStatus.DRAFT,
        parameters=_version_params(symbol), change_description=NOTE,
    )
    session.add_all([b_ver, c_ver])
    await session.flush()

    baseline = PaperSignalSession(
        strategy_version_id=b_ver.id, symbol_code=symbol, status="active",
        started_by=STARTED_BY, source_type="candidate_proposal", note=NOTE,
    )
    session.add(baseline)
    await session.flush()
    challenger = PaperSignalSession(
        strategy_version_id=c_ver.id, symbol_code=symbol, status="active",
        started_by=STARTED_BY, source_type="signal_challenger",
        baseline_session_id=baseline.id, note=NOTE,
    )
    session.add(challenger)
    await session.flush()

    # 반복 계획은 서비스 경유(검증 재사용) — prepared까지만. activate/tick 안 함. signal_service=None → 평가 도달 불가.
    plan = await PaperSignalRecurringRunService(session).create_prepared_pair_plan(
        baseline_session_id=baseline.id, challenger_session_id=challenger.id,
        interval_seconds=interval_seconds, max_runs=max_runs,
        confirmed=True, confirmed_by=STARTED_BY, note=NOTE,
    )
    return {
        "strategy_id": strat.id,
        "baseline_version_id": b_ver.id,
        "challenger_version_id": c_ver.id,
        "baseline_session_id": baseline.id,
        "challenger_session_id": challenger.id,
        "recurring_plan_id": plan["id"],
        "reused": False,
    }


def _print_human(result: dict, *, executed: bool) -> None:
    print(f"mode: {'EXECUTE (committed)' if executed else 'DRY-RUN (no DB data created)'}")
    print(f"labels: {' '.join(SYNTHETIC_LABELS)}")
    for k, v in result.items():
        print(f"  {k}: {v}")
    print("⚠ This is SYNTHETIC/DEMO setup data — NOT trading evidence, NOT real performance.")
    print("⚠ Do not use to judge profitability. Does not justify M2.14B-3d.")
    print("SignalLog=0 Trade=0 Order=0 broker/KIS calls=0 (bootstrap never ticks).")
    if not executed:
        print("Next safe action (only if you accept demo nature): run M2.14H manual tick on the prepared plan.")


async def _run_async(args) -> int:
    settings = get_settings()
    reasons = evaluate_guards(settings, confirm=args.confirm, execute=args.execute)

    if not args.execute:
        # DRY-RUN: 읽기 전용. 아무 것도 insert/commit 하지 않는다.
        async with async_session_factory() as session:
            existing = await find_existing_pair(session, args.symbol)
        plan = {
            "planned_symbol": args.symbol,
            "planned_interval_seconds": args.interval_seconds,
            "planned_max_runs": args.max_runs,
            "existing_pair": existing,
            "guards_block_execute": reasons,
            "would_create": (
                "nothing (existing synthetic pair reused)" if existing and not args.force_new
                else "Strategy x1 + StrategyVersion x2 (DRAFT) + PaperSignalSession x2 (active) + 1 prepared plan"
            ),
        }
        if args.json:
            print(json.dumps(plan, default=str, ensure_ascii=False))
        else:
            _print_human(plan, executed=False)
        return 0

    if reasons:
        print("REFUSED (hard guards):")
        for r in reasons:
            print(f"  - {r}")
        return 2

    async with async_session_factory() as session:
        try:
            result = await seed_synthetic_pair(
                session, symbol=args.symbol, interval_seconds=args.interval_seconds,
                max_runs=args.max_runs, force_new=args.force_new,
            )
            await session.commit()
        except Exception as exc:  # noqa: BLE001 - 실패 시 부분 데이터 남기지 않는다.
            await session.rollback()
            print(f"FAILED — rolled back, no data persisted: {type(exc).__name__}: {exc}")
            return 1
    if args.json:
        print(json.dumps(result, default=str, ensure_ascii=False))
    else:
        _print_human(result, executed=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Dev-only SYNTHETIC signal pair bootstrap (M2.14L). NOT trading evidence.")
    p.add_argument("--symbol", default="005930")
    p.add_argument("--interval-seconds", type=int, default=60, dest="interval_seconds")
    p.add_argument("--max-runs", type=int, default=30, dest="max_runs")
    p.add_argument("--confirm-dev-synthetic-bootstrap", action="store_true", dest="confirm")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--force-new", action="store_true", dest="force_new")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(_run_async(args))


if __name__ == "__main__":
    sys.exit(main())
