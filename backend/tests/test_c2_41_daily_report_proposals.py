"""C-2.41 일일 리포트 AI 제안 활동 집계 테스트."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import ScannerRuleStatus
from app.domain.models.scanner_proposal import ScannerRuleProposal
from app.services.daily_report_service import DailyReportService
from app.services.scanner_proposal_service import ScannerProposalService
from app.services.scanner_service import ScannerService

KST = ZoneInfo("Asia/Seoul")
REPORT_DAY = date(2026, 6, 17)


async def _make_scanner_proposal(session: AsyncSession) -> int:
    scanner = ScannerService(session)
    rule = await scanner.create_rule("vol")
    sv = await scanner.create_version(
        rule.id, conditions=[{"type": "volume_spike", "params": {"multiplier": 2.0}}],
        status=ScannerRuleStatus.TESTING,
    )
    proposal = await ScannerProposalService(session).create_proposal(
        scanner_rule_id=rule.id,
        suggested_conditions=[{"type": "volume_spike", "params": {"multiplier": 2.6}}],
        title="조건 강화",
        base_version_id=sv.id,
    )
    return proposal.id


async def test_report_counts_pending_scanner_proposals(db_session: AsyncSession) -> None:
    await _make_scanner_proposal(db_session)
    # created_at을 리포트 당일로 맞춘다.
    await db_session.execute(
        ScannerRuleProposal.__table__.update().values(
            created_at=datetime(2026, 6, 17, 10, 0, tzinfo=KST)
        )
    )
    await db_session.commit()

    report = await DailyReportService(db_session).generate(report_date=REPORT_DAY)
    pa = report.sections["proposal_activity"]
    assert pa["scanner_created"] == 1
    assert pa["scanner_pending"] == 1
    assert pa["pending_total"] == 1
    assert "검토 대기 제안 1건" in report.summary


async def test_pending_total_excludes_reviewed(db_session: AsyncSession) -> None:
    pid = await _make_scanner_proposal(db_session)
    # 승인하면 pending이 아니므로 pending_total에서 빠진다.
    await ScannerProposalService(db_session).approve(pid, reviewed_by="tester")

    report = await DailyReportService(db_session).generate(report_date=REPORT_DAY)
    pa = report.sections["proposal_activity"]
    assert pa["scanner_pending"] == 0
    assert pa["pending_total"] == 0


async def test_empty_day_has_zero_proposal_activity(db_session: AsyncSession) -> None:
    report = await DailyReportService(db_session).generate(report_date=date(2026, 6, 1))
    pa = report.sections["proposal_activity"]
    assert pa == {
        "strategy_created": 0,
        "scanner_created": 0,
        "strategy_pending": 0,
        "scanner_pending": 0,
        "pending_total": 0,
    }
