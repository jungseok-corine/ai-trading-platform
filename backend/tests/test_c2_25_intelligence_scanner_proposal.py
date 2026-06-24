"""C-2.25 Intelligence Scanner Rule Auto-Generation 테스트.

검증 항목:
1.  FakeProvider 응답으로 pending proposal이 생성됨
2.  생성된 proposal source가 "intelligence_ai"
3.  생성 직후 proposal status는 PENDING
4.  approve 시 기존 흐름대로 DRAFT version이 생성됨
5.  기존 ScannerProposalGenerator(heuristic) 흐름이 깨지지 않음
6.  pending proposal이 있는 base_version_id는 skip
7.  invalid suggested_conditions는 저장하지 않음
8.  LLM JSON 파싱 실패 시 저장하지 않고 error 반환
9.  없는 scanner_rule_id는 저장하지 않음
10. 없는 base_version_id는 저장하지 않음
11. 새 ScannerRule 생성 없음 (rule 수 불변)
12. ScannerRuleVersion ACTIVE 자동 생성 없음
13. scheduler job 기본 비활성
14. 실제 LLM 호출 없음
15. order API 호출 없음
16. broker.place_order 변경 없음
17. KIS_REAL_TRADING_ENABLED 변경 없음
"""
from __future__ import annotations

import inspect
import json
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.domain.models.enums import (
    IntelligenceEventStatus,
    IntelligenceMarketScope,
    IntelligenceProvider,
    IntelligenceSourceType,
    MarketCode,
    ProposalStatus,
    ScannerRuleStatus,
)
from app.domain.repositories.intelligence import (
    IntelligenceEventRepository,
    IntelligenceSourceRepository,
)
from app.domain.repositories.intelligence_candidate import IntelligenceCandidateRepository
from app.domain.repositories.scanner import ScannerRuleRepository, ScannerRuleVersionRepository
from app.domain.repositories.scanner_proposal import ScannerRuleProposalRepository
from app.main import app
from app.services.ai_analysis.base import AnalysisProvider
from app.services.ai_analysis.fake import FakeAnalysisProvider
from app.services.ai_analysis.schemas import AnalysisProviderResult
from app.services.intelligence_scanner_proposal_generator import (
    INTELLIGENCE_AI_SOURCE,
    IntelligenceScannerProposalGenerator,
)
from app.services.scanner_proposal_service import ScannerProposalService
from app.services.scanner_service import ScannerService
from app.db.session import get_db


# ── Fake Provider 헬퍼 ─────────────────────────────────────────────────────────

class _FixedAnalysisProvider(FakeAnalysisProvider):
    """테스트 전용: 고정된 JSON 응답을 반환하는 provider."""

    def __init__(self, response_json: list) -> None:
        self._response_content = json.dumps(response_json, ensure_ascii=False)

    async def analyze(self, prompt: str, *, model=None, timeout_seconds=None):
        return AnalysisProviderResult(
            provider="fake_fixed",
            model="fake-1.0",
            content=self._response_content,
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            latency_ms=1,
            finish_reason="stop",
            raw={},
        )


class _BadJsonProvider(FakeAnalysisProvider):
    """테스트 전용: 파싱 불가능한 응답 반환."""

    async def analyze(self, prompt: str, *, model=None, timeout_seconds=None):
        return AnalysisProviderResult(
            provider="fake_bad",
            model="fake-1.0",
            content="이것은 JSON이 아닙니다. {broken",
            prompt_tokens=5,
            completion_tokens=5,
            total_tokens=10,
            latency_ms=1,
            finish_reason="stop",
            raw={},
        )


# ── DB 세션 오버라이드 헬퍼 ────────────────────────────────────────────────────

def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


# ── 시드 헬퍼 ─────────────────────────────────────────────────────────────────

async def _seed_scanner_rule_with_active_version(
    session: AsyncSession,
    rule_name: str = "테스트 스캐너",
    status: ScannerRuleStatus = ScannerRuleStatus.ACTIVE,
) -> tuple:
    """ScannerRule + active/testing ScannerRuleVersion을 생성하고 (rule, version)을 반환."""
    scanner = ScannerService(session)
    rule = await scanner.create_rule(rule_name)
    version = await scanner.create_version(
        rule.id,
        conditions=[
            {"type": "volume_spike", "params": {"multiplier": 2.0}},
            {"type": "turnover_rank", "params": {"max_rank": 50}},
        ],
        status=status,
        change_description="초기 버전",
    )
    await session.flush()
    return rule, version


async def _seed_intelligence_candidate(
    session: AsyncSession,
    symbol_code: str = "005930",
    score: int = 80,
) -> int:
    """IntelligenceSource + IntelligenceEvent + IntelligenceCandidate를 생성하고 candidate.id 반환."""
    src_repo = IntelligenceSourceRepository(session)
    src = await src_repo.create(
        source_key=f"test_src_{symbol_code}",
        source_type=IntelligenceSourceType.NEWS,
        provider=IntelligenceProvider.RSS,
        market_scope=IntelligenceMarketScope.KR,
    )
    await session.flush()

    ev_repo = IntelligenceEventRepository(session)
    ev = await ev_repo.create(
        source_id=src.id,
        event_type="news",
        market=MarketCode.KR,
        symbol_code=symbol_code,
        title=f"{symbol_code} 관련 뉴스",
        summary="테스트 이벤트",
        dedup_hash=f"ev_hash_{symbol_code}_{score}",
        status=IntelligenceEventStatus.RAW,
    )
    await session.flush()

    cand_repo = IntelligenceCandidateRepository(session)
    cand = await cand_repo.create(
        intelligence_event_id=ev.id,
        symbol_code=symbol_code,
        market=MarketCode.KR,
        score=score,
        why_text="테스트 후보",
        source_type="news",
        matched_themes=["semiconductor"],
        score_components={"base_importance": score},
        dedup_hash=f"cand_hash_{symbol_code}_{score}",
    )
    await session.flush()
    return cand.id


# ── 테스트 ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_creates_pending_proposal(db_session: AsyncSession) -> None:
    """1. FakeProvider 응답으로 pending proposal이 생성됨."""
    rule, version = await _seed_scanner_rule_with_active_version(db_session)
    await _seed_intelligence_candidate(db_session)

    provider = _FixedAnalysisProvider([{
        "scanner_rule_id": rule.id,
        "base_version_id": version.id,
        "suggested_conditions": [
            {"type": "volume_spike", "params": {"multiplier": 3.0}},
        ],
        "title": "테스트 제안",
        "rationale": "거래량 임계 강화",
        "expected_effect": "신호 품질 향상",
    }])
    generator = IntelligenceScannerProposalGenerator(db_session, provider=provider)
    summary = await generator.generate()

    assert summary.proposals_created == 1
    assert summary.skipped_invalid == 0
    assert summary.errors == []


@pytest.mark.asyncio
async def test_generated_proposal_source_is_intelligence_ai(db_session: AsyncSession) -> None:
    """2. 생성된 proposal source가 "intelligence_ai"."""
    rule, version = await _seed_scanner_rule_with_active_version(db_session)
    await _seed_intelligence_candidate(db_session)

    provider = _FixedAnalysisProvider([{
        "scanner_rule_id": rule.id,
        "base_version_id": version.id,
        "suggested_conditions": [{"type": "volume_spike", "params": {"multiplier": 2.5}}],
        "title": "source 확인 테스트",
        "rationale": "reason",
        "expected_effect": "effect",
    }])
    generator = IntelligenceScannerProposalGenerator(db_session, provider=provider)
    await generator.generate()

    repo = ScannerRuleProposalRepository(db_session)
    proposals = await repo.list_filtered(scanner_rule_id=rule.id)
    assert len(proposals) == 1
    assert proposals[0].source == INTELLIGENCE_AI_SOURCE


@pytest.mark.asyncio
async def test_proposal_status_is_pending_after_creation(db_session: AsyncSession) -> None:
    """3. 생성 직후 proposal status는 PENDING."""
    rule, version = await _seed_scanner_rule_with_active_version(db_session)
    await _seed_intelligence_candidate(db_session)

    provider = _FixedAnalysisProvider([{
        "scanner_rule_id": rule.id,
        "base_version_id": version.id,
        "suggested_conditions": [{"type": "price_change_pct", "params": {"min_pct": 5.0}}],
        "title": "상승률 필터 추가",
        "rationale": "reason",
        "expected_effect": "effect",
    }])
    generator = IntelligenceScannerProposalGenerator(db_session, provider=provider)
    await generator.generate()

    repo = ScannerRuleProposalRepository(db_session)
    proposals = await repo.list_filtered(scanner_rule_id=rule.id)
    assert proposals[0].status == ProposalStatus.PENDING


@pytest.mark.asyncio
async def test_approve_creates_draft_version(db_session: AsyncSession) -> None:
    """4. approve 시 기존 흐름대로 DRAFT version이 생성됨."""
    rule, version = await _seed_scanner_rule_with_active_version(db_session)
    await _seed_intelligence_candidate(db_session)

    provider = _FixedAnalysisProvider([{
        "scanner_rule_id": rule.id,
        "base_version_id": version.id,
        "suggested_conditions": [{"type": "volume_spike", "params": {"multiplier": 4.0}}],
        "title": "승인 흐름 테스트",
        "rationale": "reason",
        "expected_effect": "effect",
    }])
    generator = IntelligenceScannerProposalGenerator(db_session, provider=provider)
    await generator.generate()

    repo = ScannerRuleProposalRepository(db_session)
    proposals = await repo.list_filtered(scanner_rule_id=rule.id)
    proposal = proposals[0]

    svc = ScannerProposalService(db_session)
    approved, new_version = await svc.approve(proposal.id, reviewed_by="test_user")

    assert approved.status == ProposalStatus.APPROVED
    assert new_version.status == ScannerRuleStatus.DRAFT
    assert new_version.scanner_rule_id == rule.id


@pytest.mark.asyncio
async def test_heuristic_generator_still_works(db_session: AsyncSession) -> None:
    """5. 기존 ScannerProposalGenerator(heuristic) 흐름이 깨지지 않음."""
    from app.services.scanner_proposal_generator import ScannerProposalGenerator

    # heuristic generator는 인스턴스화만 하고 데이터 없이도 에러가 나지 않아야 한다.
    generator = ScannerProposalGenerator(db_session)
    assert generator is not None
    # generate_for_version은 별도 테스트(C-2.39)에서 검증됨 — 여기서는 클래스 import만 확인.


@pytest.mark.asyncio
async def test_skips_version_with_existing_pending_proposal(db_session: AsyncSession) -> None:
    """6. pending proposal이 있는 base_version_id는 skip."""
    rule, version = await _seed_scanner_rule_with_active_version(db_session)
    await _seed_intelligence_candidate(db_session)

    # 먼저 pending 제안을 수동으로 생성
    svc = ScannerProposalService(db_session)
    await svc.create_proposal(
        scanner_rule_id=rule.id,
        suggested_conditions=[{"type": "volume_spike", "params": {"multiplier": 3.0}}],
        title="기존 pending 제안",
        base_version_id=version.id,
        source="manual",
    )
    await db_session.flush()

    # 같은 base_version_id로 생성 시도 → skip
    provider = _FixedAnalysisProvider([{
        "scanner_rule_id": rule.id,
        "base_version_id": version.id,
        "suggested_conditions": [{"type": "volume_spike", "params": {"multiplier": 4.0}}],
        "title": "중복 시도",
        "rationale": "reason",
        "expected_effect": "effect",
    }])
    generator = IntelligenceScannerProposalGenerator(db_session, provider=provider)
    summary = await generator.generate()

    assert summary.proposals_created == 0
    assert summary.skipped_existing_pending == 1


@pytest.mark.asyncio
async def test_invalid_conditions_not_saved(db_session: AsyncSession) -> None:
    """7. invalid suggested_conditions는 저장하지 않음."""
    rule, version = await _seed_scanner_rule_with_active_version(db_session)
    await _seed_intelligence_candidate(db_session)

    # volume_spike에 multiplier 누락 → InvalidConditionError
    provider = _FixedAnalysisProvider([{
        "scanner_rule_id": rule.id,
        "base_version_id": version.id,
        "suggested_conditions": [{"type": "volume_spike", "params": {}}],
        "title": "invalid 조건",
        "rationale": "reason",
        "expected_effect": "effect",
    }])
    generator = IntelligenceScannerProposalGenerator(db_session, provider=provider)
    summary = await generator.generate()

    assert summary.proposals_created == 0
    assert summary.skipped_invalid == 1
    assert any("조건 검증 실패" in e for e in summary.errors)


@pytest.mark.asyncio
async def test_json_parse_failure_returns_error(db_session: AsyncSession) -> None:
    """8. LLM JSON 파싱 실패 시 저장하지 않고 error 반환."""
    rule, version = await _seed_scanner_rule_with_active_version(db_session)
    await _seed_intelligence_candidate(db_session)

    generator = IntelligenceScannerProposalGenerator(db_session, provider=_BadJsonProvider())
    summary = await generator.generate()

    assert summary.proposals_created == 0
    assert any("JSON 파싱 실패" in e for e in summary.errors)


@pytest.mark.asyncio
async def test_unknown_scanner_rule_id_skipped(db_session: AsyncSession) -> None:
    """9. 없는 scanner_rule_id는 저장하지 않음."""
    rule, version = await _seed_scanner_rule_with_active_version(db_session)
    await _seed_intelligence_candidate(db_session)

    provider = _FixedAnalysisProvider([{
        "scanner_rule_id": 99999,
        "base_version_id": version.id,
        "suggested_conditions": [{"type": "volume_spike", "params": {"multiplier": 2.0}}],
        "title": "없는 룰 id",
        "rationale": "reason",
        "expected_effect": "effect",
    }])
    generator = IntelligenceScannerProposalGenerator(db_session, provider=provider)
    summary = await generator.generate()

    assert summary.proposals_created == 0
    assert summary.skipped_invalid == 1


@pytest.mark.asyncio
async def test_unknown_base_version_id_skipped(db_session: AsyncSession) -> None:
    """10. 없는 base_version_id는 저장하지 않음."""
    rule, version = await _seed_scanner_rule_with_active_version(db_session)
    await _seed_intelligence_candidate(db_session)

    provider = _FixedAnalysisProvider([{
        "scanner_rule_id": rule.id,
        "base_version_id": 99999,
        "suggested_conditions": [{"type": "volume_spike", "params": {"multiplier": 2.0}}],
        "title": "없는 version id",
        "rationale": "reason",
        "expected_effect": "effect",
    }])
    generator = IntelligenceScannerProposalGenerator(db_session, provider=provider)
    summary = await generator.generate()

    assert summary.proposals_created == 0
    assert summary.skipped_invalid == 1


@pytest.mark.asyncio
async def test_no_new_scanner_rule_created(db_session: AsyncSession) -> None:
    """11. 새 ScannerRule 생성 없음 — 생성 전후 rule 수 동일."""
    rule, version = await _seed_scanner_rule_with_active_version(db_session)
    await _seed_intelligence_candidate(db_session)

    rule_repo = ScannerRuleRepository(db_session)
    rules_before = await rule_repo.list_with_version_counts()
    count_before = len(rules_before)

    provider = _FixedAnalysisProvider([{
        "scanner_rule_id": rule.id,
        "base_version_id": version.id,
        "suggested_conditions": [{"type": "volume_spike", "params": {"multiplier": 3.0}}],
        "title": "룰 수 변경 없음 확인",
        "rationale": "reason",
        "expected_effect": "effect",
    }])
    generator = IntelligenceScannerProposalGenerator(db_session, provider=provider)
    await generator.generate()

    rules_after = await rule_repo.list_with_version_counts()
    assert len(rules_after) == count_before


@pytest.mark.asyncio
async def test_no_active_version_auto_created(db_session: AsyncSession) -> None:
    """12. ScannerRuleVersion ACTIVE 자동 생성 없음 — 제안만 pending으로 저장됨."""
    rule, version = await _seed_scanner_rule_with_active_version(db_session)
    await _seed_intelligence_candidate(db_session)

    version_repo = ScannerRuleVersionRepository(db_session)
    versions_before = await version_repo.list_active()
    active_before = len(versions_before)

    provider = _FixedAnalysisProvider([{
        "scanner_rule_id": rule.id,
        "base_version_id": version.id,
        "suggested_conditions": [{"type": "volume_spike", "params": {"multiplier": 3.0}}],
        "title": "auto-active 없음 확인",
        "rationale": "reason",
        "expected_effect": "effect",
    }])
    generator = IntelligenceScannerProposalGenerator(db_session, provider=provider)
    summary = await generator.generate()

    # 제안은 생성되지만 active version 수는 그대로
    assert summary.proposals_created == 1
    versions_after = await version_repo.list_active()
    assert len(versions_after) == active_before


def test_intelligence_scanner_proposal_scheduler_default_disabled() -> None:
    """13. intelligence_scanner_proposal 스케줄러 잡은 기본 비활성."""
    settings = Settings(_env_file=None)
    assert settings.intelligence_scanner_proposal_scheduler_enabled is False


def test_no_real_llm_call_in_service() -> None:
    """14. 실제 LLM 호출 없음 — provider.analyze가 외부 네트워크를 사용하지 않는다.

    서비스 소스 코드에서 직접 httpx/requests/urllib 등 HTTP 라이브러리가
    intelligence_scanner_proposal_generator 안에서 import되지 않는지 확인한다.
    """
    import app.services.intelligence_scanner_proposal_generator as mod
    src = inspect.getsource(mod)
    for banned in ("requests.get", "requests.post", "httpx.get", "httpx.post", "urllib.request"):
        assert banned not in src, f"{banned}가 generator 코드에 있음 — 직접 HTTP 호출 금지"


def test_no_order_api_in_service() -> None:
    """15. order API 호출 없음."""
    import app.services.intelligence_scanner_proposal_generator as mod
    src = inspect.getsource(mod)
    forbidden = ["TTTC0012U", "TTTC0011U", "VTTC0012U", "VTTC0011U", "place_order"]
    for sym in forbidden:
        assert sym not in src, f"{sym}가 generator 코드에 있음"


def test_broker_place_order_not_in_service() -> None:
    """16. broker.place_order 변경 없음."""
    import app.services.intelligence_scanner_proposal_generator as mod
    src = inspect.getsource(mod)
    assert "place_order" not in src


def test_kis_real_trading_enabled_not_changed() -> None:
    """17. KIS_REAL_TRADING_ENABLED 변경 없음 — 기본값 False 유지."""
    settings = Settings(_env_file=None)
    assert settings.kis_real_trading_enabled is False


# ── API 엔드포인트 테스트 ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_generate_endpoint_returns_summary(db_session: AsyncSession) -> None:
    """POST /intelligence/scanner-proposals/generate 가 summary를 반환한다."""
    rule, version = await _seed_scanner_rule_with_active_version(db_session)
    await _seed_intelligence_candidate(db_session)
    await db_session.flush()

    # 빈 active 버전이 있으면 LLM은 fake provider가 처리 (기본값 ai_analysis_provider=fake)
    # FakeProvider는 비-JSON 응답을 반환하므로 proposals_created=0이 정상
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/intelligence/scanner-proposals/generate",
                json={"candidate_limit": 10},
            )
        assert resp.status_code == 201
        body = resp.json()
        assert "candidates_analyzed" in body
        assert "proposals_created" in body
        assert "errors" in body
    finally:
        app.dependency_overrides.pop(get_db, None)
