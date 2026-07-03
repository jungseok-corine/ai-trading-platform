"""C-6.17: 스캐너 후보 기근 감지 → 조건 완화 제안.

배경: 자동 점검(C-2.39)은 강화만 있어서, 조건이 시장 위로 올라가면
후보 0건에 영구히 갇힌다 (2026-06-23 실사례 — 10일간 후보 0건).
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.enums import ScannerRuleStatus
from app.domain.models.scanner import ScannerRule, ScannerRuleVersion
from app.services.scanner_proposal_generator import (
    ScannerProposalGenerator,
    loosen_conditions,
)

# ── loosen_conditions 순수 함수 ─────────────────────────────────────────


def test_loosen_reverses_tighten_direction():
    conds = [
        {"type": "volume_spike", "params": {"multiplier": 2.6}},
        {"type": "price_change_pct", "params": {"min_pct": 3.0}},
        {"type": "turnover_rank", "params": {"max_rank": 35}},
    ]
    result = loosen_conditions(conds)
    assert result.conditions[0]["params"]["multiplier"] == 2.0  # 2.6/1.3
    assert result.conditions[1]["params"]["min_pct"] == 2.3  # 3.0/1.3
    assert result.conditions[2]["params"]["max_rank"] == 50  # 35/0.7
    assert len(result.changes) == 3


def test_loosen_respects_floors():
    """하한(무의미한 수준) 아래로는 완화하지 않는다."""
    conds = [
        {"type": "volume_spike", "params": {"multiplier": 1.2}},
        {"type": "price_change_pct", "params": {"min_pct": 0.5}},
        {"type": "turnover_rank", "params": {"max_rank": 100}},
    ]
    result = loosen_conditions(conds)
    assert result.changes == []  # 이미 하한 — 변경 없음
    assert result.conditions[0]["params"]["multiplier"] == 1.2


def test_loosen_keeps_categorical_conditions():
    conds = [{"type": "investor_flow", "params": {"mode": "foreign"}}]
    result = loosen_conditions(conds)
    assert result.conditions == conds
    assert result.changes == []


# ── 기근 감지 → 완화 제안 ───────────────────────────────────────────────


async def _rule_version(session: AsyncSession, conditions: list[dict]) -> ScannerRuleVersion:
    rule = ScannerRule(name="drought test")
    session.add(rule)
    await session.flush()
    version = ScannerRuleVersion(
        scanner_rule_id=rule.id, version_no=1, conditions=conditions,
        status=ScannerRuleStatus.TESTING,
    )
    session.add(version)
    await session.commit()
    return version


@pytest.mark.asyncio
async def test_drought_generates_loosening_proposal(db_session: AsyncSession):
    version = await _rule_version(
        db_session, [{"type": "volume_spike", "params": {"multiplier": 2.6}}]
    )
    # 후보 0건 (기근) → 완화 제안
    proposal = await ScannerProposalGenerator(db_session).generate_for_version(version.id)
    assert proposal is not None
    assert proposal.status.value == "pending"  # 승인은 사람
    assert "완화" in proposal.title
    assert proposal.suggested_conditions[0]["params"]["multiplier"] == 2.0


@pytest.mark.asyncio
async def test_no_drought_when_recent_candidates_exist(db_session: AsyncSession):
    version = await _rule_version(
        db_session, [{"type": "volume_spike", "params": {"multiplier": 2.6}}]
    )
    db_session.add(
        CandidateEvent(
            scanner_rule_version_id=version.id, symbol_code="005930",
            triggered_at=datetime.now(timezone.utc) - timedelta(days=1),
            score=80, matched_conditions=["volume_spike"],
        )
    )
    await db_session.commit()
    # 후보 있음 + 표본 부족(1 < 5) → 기근 아님 + 강화도 안 함 → None
    proposal = await ScannerProposalGenerator(db_session).generate_for_version(version.id)
    assert proposal is None


@pytest.mark.asyncio
async def test_drought_at_floor_no_proposal(db_session: AsyncSession):
    """기근이어도 이미 하한이면 제안하지 않는다 (무한 완화 방지)."""
    version = await _rule_version(
        db_session, [{"type": "volume_spike", "params": {"multiplier": 1.2}}]
    )
    proposal = await ScannerProposalGenerator(db_session).generate_for_version(version.id)
    assert proposal is None
