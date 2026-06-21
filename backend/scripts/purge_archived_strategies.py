"""C-4 정리: 아카이브된 토이 전략 하드 삭제(목록에서 완전 제거).

대상: 살아있는 버전(DRAFT/TESTING/ACTIVE/RETIRED)이 하나도 없는 전략.
      즉 모든 버전이 ARCHIVED 이거나, 버전이 0개인 전략(빈 껍데기).
      → 새로 만든 유니버스 전략(TESTING)이나 운영 중 버전이 있는 전략은 절대 삭제하지 않는다.

부모 strategies 행을 삭제하면 DB FK 제약에 따라:
  - strategy_versions: CASCADE 삭제
  - experiment_variants / promotion: CASCADE 삭제(해당 버전에 묶인 것)
  - trades / strategy_proposals / ai_analysis / signal_logs / risk: SET NULL
되돌릴 수 없다.

기본 dry-run(목록만 출력). --apply 지정 시에만 실제 삭제.

사용법:
    .venv/bin/python scripts/purge_archived_strategies.py
    .venv/bin/python scripts/purge_archived_strategies.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

_ENV_FILE = _BACKEND_DIR / ".env"
if _ENV_FILE.exists():
    from dotenv import load_dotenv  # type: ignore[import-untyped]

    load_dotenv(dotenv_path=_ENV_FILE, override=False)


@dataclass
class PurgeTarget:
    strategy_id: int
    name: str
    version_count: int


async def _find_targets(session) -> list[PurgeTarget]:
    from sqlalchemy import func, select

    from app.domain.models.enums import StrategyVersionStatus
    from app.domain.models.strategy import Strategy, StrategyVersion

    live = (
        StrategyVersionStatus.DRAFT,
        StrategyVersionStatus.TESTING,
        StrategyVersionStatus.ACTIVE,
        StrategyVersionStatus.RETIRED,
    )
    # 살아있는 버전이 하나라도 있으면 제외(NOT EXISTS).
    has_live = (
        select(StrategyVersion.id)
        .where(StrategyVersion.strategy_id == Strategy.id)
        .where(StrategyVersion.status.in_(live))
        .exists()
    )
    vcount = (
        select(func.count())
        .select_from(StrategyVersion)
        .where(StrategyVersion.strategy_id == Strategy.id)
        .scalar_subquery()
    )
    stmt = select(Strategy.id, Strategy.name, vcount).where(~has_live).order_by(Strategy.id)
    rows = await session.execute(stmt)
    return [PurgeTarget(strategy_id=r[0], name=r[1], version_count=int(r[2])) for r in rows.all()]


async def run(session, *, apply: bool) -> list[PurgeTarget]:
    from sqlalchemy import delete

    from app.domain.models.strategy import Strategy

    targets = await _find_targets(session)
    if apply and targets:
        ids = [t.strategy_id for t in targets]
        # 부모 삭제 → 버전/실험variant/승격은 CASCADE, 나머지는 SET NULL (DB FK 제약).
        await session.execute(delete(Strategy).where(Strategy.id.in_(ids)))
        await session.commit()
    return targets


def _print(targets: list[PurgeTarget], *, dry_run: bool) -> None:
    mode = "[DRY-RUN]" if dry_run else "[DELETED]"
    total_versions = sum(t.version_count for t in targets)
    print(f"\n{'=' * 64}\n아카이브 전략 하드 삭제 {mode}\n{'=' * 64}")
    if not targets:
        print("  삭제 대상 없음. (살아있는 버전이 없는 전략이 없습니다.)")
    else:
        for t in targets:
            print(f"  🗑️  [strategy#{t.strategy_id}] {t.name}  (버전 {t.version_count}개)")
        print(f"\n  전략 {len(targets)}개 + 버전 {total_versions}개 삭제 대상.")
        print("  ※ 연관 실험 variant/결과·승격(promotion) 기록은 CASCADE로 함께 삭제됩니다.")
        print("  ※ trades/proposals/ai_analysis는 NULL 처리(이력 행 자체는 보존).")
    print("=" * 64)
    if dry_run and targets:
        print("dry-run 입니다. 실제 삭제하려면 --apply 를 붙여 다시 실행하세요(되돌릴 수 없음).")


async def main(apply: bool) -> int:
    from app.db.session import async_session_factory, engine

    if apply:
        print("\n⚠️  APPLY 모드: 전략이 영구 삭제됩니다(되돌릴 수 없음). 중단하려면 Ctrl-C.")
        try:
            input("계속하려면 Enter... ")
        except (KeyboardInterrupt, EOFError):
            print("\n중단됨.")
            return 1

    async with async_session_factory() as session:
        targets = await run(session, apply=apply)
    await engine.dispose()
    _print(targets, dry_run=not apply)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="C-4: 아카이브된 토이 전략 하드 삭제")
    parser.add_argument("--apply", action="store_true", default=False, help="실제 삭제. 미지정 시 dry-run.")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply)))
