#!/usr/bin/env python
"""C-4 정리: 토이 전략 아카이브 + 노이즈 매매로그 리셋.

기본 dry-run(DB 수정 없음, 대상 건수만 출력). --apply 지정 시에만 실제 변경.

  아카이브: 기존 strategy_versions(DRAFT/TESTING/ACTIVE)를 ARCHIVED로 전환하고
            parameters.auto_trade_enabled=false. 이력/FK는 보존되며 되돌릴 수 있다.
  리셋(삭제): signal_logs 전체 + PAPER 계좌의 trades/positions/position_events.
            (--reset-experiments 지정 시 experiments/variants/results도 삭제.)

안전:
  - LIVE 계좌(실계좌 read-only 동기화 데이터)의 trades/positions는 절대 삭제하지 않는다.
  - 실주문 API 호출 없음. KIS_REAL_TRADING_ENABLED 등 안전 불변식과 무관한 데이터 작업.
  - --apply는 명시적 확인(Enter)을 요구하고 단일 트랜잭션으로 처리한다.

사용법:
    PYTHONPATH=backend python backend/scripts/reset_toy_strategies.py
    PYTHONPATH=backend python backend/scripts/reset_toy_strategies.py --apply
    PYTHONPATH=backend python backend/scripts/reset_toy_strategies.py --apply --reset-experiments
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

# ruff: noqa: E402  (sys.path 조작이 import 전에 필요)
sys.path.insert(0, __file__.split("/scripts/")[0])

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, StrategyVersionStatus
from app.domain.models.experiment import Experiment, ExperimentResult, ExperimentVariant
from app.domain.models.position import Position
from app.domain.models.position_event import PositionEvent
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import StrategyVersion
from app.domain.models.trade import Trade
from scripts._common import db_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# 아카이브 대상이 되는(아직 살아있는) 전략 버전 상태.
_ARCHIVABLE = (
    StrategyVersionStatus.DRAFT,
    StrategyVersionStatus.TESTING,
    StrategyVersionStatus.ACTIVE,
)


async def _count(session: AsyncSession, stmt) -> int:
    return int((await session.execute(stmt)).scalar_one())


async def _paper_account_ids(session: AsyncSession) -> list[int]:
    rows = await session.execute(
        select(Account.id).where(Account.account_type == AccountType.PAPER)
    )
    return [r[0] for r in rows.all()]


async def run(session: AsyncSession, *, apply: bool, reset_experiments: bool) -> dict[str, int]:
    paper_ids = await _paper_account_ids(session)

    # --- 집계(dry-run/apply 공통) ---
    archive_n = await _count(
        session,
        select(func.count()).select_from(StrategyVersion).where(
            StrategyVersion.status.in_(_ARCHIVABLE)
        ),
    )
    signal_n = await _count(session, select(func.count()).select_from(SignalLog))

    if paper_ids:
        trade_n = await _count(
            session,
            select(func.count()).select_from(Trade).where(Trade.account_id.in_(paper_ids)),
        )
        pos_n = await _count(
            session,
            select(func.count()).select_from(Position).where(Position.account_id.in_(paper_ids)),
        )
        pevent_n = await _count(
            session,
            select(func.count())
            .select_from(PositionEvent)
            .join(Position, Position.id == PositionEvent.position_id)
            .where(Position.account_id.in_(paper_ids)),
        )
    else:
        trade_n = pos_n = pevent_n = 0

    exp_n = await _count(session, select(func.count()).select_from(Experiment)) if reset_experiments else 0

    counts = {
        "archive_strategy_versions": archive_n,
        "delete_signal_logs": signal_n,
        "delete_paper_trades": trade_n,
        "delete_paper_positions": pos_n,
        "delete_paper_position_events": pevent_n,
        "delete_experiments": exp_n,
    }

    if not apply:
        return counts

    # --- 실제 적용 (단일 트랜잭션) ---
    # 1) 전략 아카이브 + auto_trade off
    versions = (
        await session.execute(
            select(StrategyVersion).where(StrategyVersion.status.in_(_ARCHIVABLE))
        )
    ).scalars().all()
    for v in versions:
        v.status = StrategyVersionStatus.ARCHIVED
        v.parameters = {**(v.parameters or {}), "auto_trade_enabled": False}

    # 2) 노이즈 로그 삭제 (자식→부모 순서; position_events는 positions CASCADE로 함께 삭제됨)
    await session.execute(delete(SignalLog))
    if paper_ids:
        # position_events는 positions(ondelete=CASCADE) 삭제 시 함께 제거되지만, 명시적으로도 삭제.
        await session.execute(
            delete(PositionEvent).where(
                PositionEvent.position_id.in_(
                    select(Position.id).where(Position.account_id.in_(paper_ids))
                )
            )
        )
        await session.execute(delete(Position).where(Position.account_id.in_(paper_ids)))
        await session.execute(delete(Trade).where(Trade.account_id.in_(paper_ids)))

    # 3) 실험 기록 (옵션)
    if reset_experiments:
        await session.execute(delete(ExperimentResult))
        await session.execute(delete(ExperimentVariant))
        await session.execute(delete(Experiment))

    await session.commit()
    return counts


def _print(counts: dict[str, int], *, dry_run: bool, reset_experiments: bool) -> None:
    mode = "[DRY-RUN]" if dry_run else "[APPLIED]"
    print(f"\n{'=' * 60}\nC-4 정리 {mode}\n{'=' * 60}")
    print(f"  아카이브할 전략 버전(→ARCHIVED, auto_trade off): {counts['archive_strategy_versions']}")
    print(f"  삭제할 signal_logs(전체)                       : {counts['delete_signal_logs']}")
    print(f"  삭제할 PAPER trades                            : {counts['delete_paper_trades']}")
    print(f"  삭제할 PAPER positions                         : {counts['delete_paper_positions']}")
    print(f"  삭제할 PAPER position_events                   : {counts['delete_paper_position_events']}")
    if reset_experiments:
        print(f"  삭제할 experiments(+variants/results)          : {counts['delete_experiments']}")
    print("  ※ LIVE 계좌 데이터는 건드리지 않습니다.")
    print("=" * 60)
    if dry_run:
        print("dry-run 입니다. 실제 적용하려면 --apply 를 붙여 다시 실행하세요.")


async def main(apply: bool, reset_experiments: bool) -> int:
    if apply:
        print("\n⚠️  APPLY 모드: DB가 변경됩니다(전략 아카이브 + 로그 삭제). 중단하려면 Ctrl-C.")
        try:
            input("계속하려면 Enter... ")
        except (KeyboardInterrupt, EOFError):
            print("\n중단됨.")
            return 1

    async with db_session() as session:
        counts = await run(session, apply=apply, reset_experiments=reset_experiments)

    _print(counts, dry_run=not apply, reset_experiments=reset_experiments)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="C-4 정리: 토이 전략 아카이브 + 노이즈 로그 리셋")
    parser.add_argument("--apply", action="store_true", default=False, help="DB를 실제로 변경한다. 미지정 시 dry-run.")
    parser.add_argument(
        "--reset-experiments", action="store_true", default=False,
        help="experiments/variants/results 도 함께 삭제한다(기본: 보존).",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply, reset_experiments=args.reset_experiments)))
