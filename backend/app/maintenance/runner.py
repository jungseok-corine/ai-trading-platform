"""Maintenance 실행 오케스트레이터."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.maintenance.checks import (
    Finding,
    detect_null_risk_events,
    detect_orphan_strategy_versions,
    detect_placeholder_accounts,
    detect_position_event_mismatches,
)
from app.maintenance.db_queries import (
    apply_null_risk_event_fix,
    apply_orphan_strategy_version_disable,
    apply_position_mismatch_adjustment,
    fetch_account_inputs,
    fetch_active_strategy_version_inputs,
    fetch_null_risk_event_inputs,
    fetch_position_mismatch_inputs,
    fetch_watchlist_symbol_codes,
)

log = logging.getLogger(__name__)


@dataclass
class MaintenanceReport:
    findings: list[Finding] = field(default_factory=list)
    applied: dict[str, int] = field(default_factory=dict)

    @property
    def total_findings(self) -> int:
        return len(self.findings)

    @property
    def auto_fixable_count(self) -> int:
        return sum(1 for f in self.findings if f.auto_fixable)


async def run_maintenance(
    session: AsyncSession,
    dry_run: bool = True,
) -> MaintenanceReport:
    report = MaintenanceReport()
    mode = "dry-run" if dry_run else "apply"
    log.info("=== Maintenance run starting (mode=%s) ===", mode)

    # 1. NULL risk_events
    null_inputs = await fetch_null_risk_event_inputs(session)
    findings_1 = detect_null_risk_events(null_inputs)
    report.findings.extend(findings_1)
    fixable_ids = [int(f.entity_id) for f in findings_1 if f.auto_fixable]
    await apply_null_risk_event_fix(session, fixable_ids, dry_run=dry_run)
    if not dry_run and fixable_ids:
        report.applied["null_risk_events"] = len(fixable_ids)

    # 2. position 수량 불일치
    mismatches = await fetch_position_mismatch_inputs(session)
    findings_2 = detect_position_event_mismatches(mismatches)
    report.findings.extend(findings_2)
    await apply_position_mismatch_adjustment(session, mismatches, dry_run=dry_run)
    if not dry_run and mismatches:
        report.applied["position_mismatches"] = len(mismatches)

    # 3. orphan strategy_versions
    versions = await fetch_active_strategy_version_inputs(session)
    watchlist_codes = await fetch_watchlist_symbol_codes(session)
    findings_3 = detect_orphan_strategy_versions(versions, watchlist_codes)
    report.findings.extend(findings_3)
    orphan_ids = [int(f.entity_id) for f in findings_3 if f.auto_fixable]
    await apply_orphan_strategy_version_disable(session, orphan_ids, dry_run=dry_run)
    if not dry_run and orphan_ids:
        report.applied["orphan_strategy_versions"] = len(orphan_ids)

    # 4. placeholder 계정 (자동 수정 없음)
    account_inputs = await fetch_account_inputs(session)
    findings_4 = detect_placeholder_accounts(account_inputs)
    report.findings.extend(findings_4)

    if not dry_run:
        await session.commit()

    log.info(
        "=== Maintenance complete: %d findings (%d auto-fixable) ===",
        report.total_findings,
        report.auto_fixable_count,
    )
    return report
