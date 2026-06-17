#!/usr/bin/env python
"""운영 DB 데이터 정리 CLI.

기본: dry-run (DB 수정 없음, 문제 목록만 출력)
적용: --apply 플래그 (명시적으로 실행할 때만 DB 수정)

사용법:
    PYTHONPATH=backend python backend/scripts/maintenance.py
    PYTHONPATH=backend python backend/scripts/maintenance.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

# ruff: noqa: E402  (sys.path 조작이 import 전에 필요)
sys.path.insert(0, __file__.split("/scripts/")[0])

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
from app.maintenance.checks import Severity
from app.maintenance.runner import MaintenanceReport, run_maintenance

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

_ICON = {
    Severity.ERROR: "🔴",
    Severity.WARNING: "🟡",
    Severity.INFO: "⚪",
}


def _print_report(report: MaintenanceReport, dry_run: bool) -> None:
    mode_label = "[DRY-RUN]" if dry_run else "[APPLIED]"
    print(f"\n{'='*60}")
    print(f"Maintenance Report {mode_label}")
    print(f"Total findings: {report.total_findings}  (auto-fixable: {report.auto_fixable_count})")
    print("=" * 60)

    if not report.findings:
        print("  ✅ No issues found.")
    else:
        for f in report.findings:
            icon = _ICON.get(f.severity, "⚪")
            fix_tag = "[fixable]" if f.auto_fixable else "[manual]"
            print(f"  {icon} {fix_tag} [{f.entity_type}#{f.entity_id}] {f.description}")

    if report.applied:
        print("\nApplied fixes:")
        for key, count in report.applied.items():
            print(f"  • {key}: {count} items")

    print("=" * 60)


async def main(apply: bool) -> int:
    dry_run = not apply

    if not dry_run:
        print("\n⚠️  APPLY MODE: DB will be modified. Ctrl-C to abort.")
        try:
            input("Press Enter to continue... ")
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            return 1

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        report = await run_maintenance(session, dry_run=dry_run)

    await engine.dispose()
    _print_report(report, dry_run)
    return 0 if report.total_findings == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Trading Platform maintenance checks")
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="DB를 실제로 수정한다. 미지정 시 dry-run.",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply)))
