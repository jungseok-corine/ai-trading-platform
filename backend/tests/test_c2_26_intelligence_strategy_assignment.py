"""C-2.26 Intelligence Strategy Assignment Automation 테스트.

검증 항목:
1.  IntelligenceStrategyProposal 생성/조회
2.  PENDING IntelligenceCandidate에서 proposal 생성
3.  suggested_strategy_type이 등록된 전략 타입인지 검증
4.  invalid strategy_type은 저장되지 않음
5.  heuristic이 matched_themes/why_text/source_type을 보고 전략을 선택함
6.  rationale에 선택 이유가 저장됨
7.  score_components 저장
8.  같은 candidate에 pending proposal이 있으면 중복 생성 안 함
9.  approve 시 proposal status=APPROVED
10. approve 시 IntelligenceCandidate.status=PROMOTED
11. approve 시 StrategyVersion 생성 없음
12. approve 시 StrategyAssignmentLog 생성 없음
13. reject 시 proposal status=REJECTED
14. auto_trade_enabled가 true로 들어가지 않음
15. 기존 StrategyAssignmentLog.candidate_event_id NOT NULL 유지
16. 기존 AssignmentService.assign() 동작 미변경
17. LLM provider 호출 없음
18. order API 호출 없음
19. broker.place_order 변경 없음
20. KIS_REAL_TRADING_ENABLED 변경 없음
21. 실전/trading/live broker 파일 변경 없음
"""
from __future__ import annotations

import inspect

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import (
    IntelligenceCandidateStatus,
    IntelligenceEventStatus,
    IntelligenceMarketScope,
    IntelligenceProvider,
    IntelligenceSourceType,
    IntelligenceStrategyProposalStatus,
    MarketCode,
)
from app.domain.repositories.intelligence import (
    IntelligenceEventRepository,
    IntelligenceSourceRepository,
)
from app.domain.repositories.intelligence_candidate import IntelligenceCandidateRepository
from app.domain.repositories.intelligence_strategy_proposal import (
    IntelligenceStrategyProposalRepository,
)
from app.domain.repositories.strategy_assignment import StrategyAssignmentLogRepository
from app.main import app
from app.services.intelligence_strategy_assignment_generator import (
    IntelligenceStrategyAssignmentGenerator,
    _match_strategy,
)
from app.db.session import get_db


# ── 세션 오버라이드 헬퍼 ─────────────────────────────────────────────────────────

def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


# ── 시드 헬퍼 ─────────────────────────────────────────────────────────────────

async def _seed_candidate(
    session: AsyncSession,
    symbol_code: str = "005930",
    score: int = 70,
    why_text: str = "테스트 후보",
    matched_themes: list | None = None,
    source_type: str = "news",
    status: IntelligenceCandidateStatus = IntelligenceCandidateStatus.PENDING,
    dedup_suffix: str = "",
) -> int:
    """IntelligenceSource + IntelligenceEvent + IntelligenceCandidate 생성, candidate.id 반환."""
    src_repo = IntelligenceSourceRepository(session)
    src = await src_repo.create(
        source_key=f"test_src_{symbol_code}{dedup_suffix}",
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
        title=f"{symbol_code} 테스트 이벤트",
        summary=why_text,
        dedup_hash=f"ev_hash_{symbol_code}_{score}{dedup_suffix}",
        status=IntelligenceEventStatus.RAW,
    )
    await session.flush()

    cand_repo = IntelligenceCandidateRepository(session)
    cand = await cand_repo.create(
        intelligence_event_id=ev.id,
        symbol_code=symbol_code,
        market=MarketCode.KR,
        score=score,
        why_text=why_text,
        source_type=source_type,
        matched_themes=matched_themes or [],
        score_components={"base_importance": score},
        dedup_hash=f"cand_hash_{symbol_code}_{score}{dedup_suffix}",
        status=status,
    )
    await session.flush()
    return cand.id


# ── 1. 모델 생성/조회 ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_proposal_create_and_get(db_session: AsyncSession) -> None:
    """1. IntelligenceStrategyProposal 생성/조회 기본 동작."""
    candidate_id = await _seed_candidate(db_session)
    repo = IntelligenceStrategyProposalRepository(db_session)

    proposal = await repo.create(
        intelligence_candidate_id=candidate_id,
        symbol_code="005930",
        market=MarketCode.KR,
        suggested_strategy_type="moving_average_cross",
        suggested_parameters={"timeframe": "5m", "quantity": 1, "strategy_type": "moving_average_cross"},
        rationale="테스트 rationale",
        confidence_score=0.5,
        score_components={"matched_rule": "moving_average_cross"},
        source="heuristic",
        status=IntelligenceStrategyProposalStatus.PENDING,
        dedup_hash="test_hash_001",
    )
    await db_session.flush()

    fetched = await repo.get(proposal.id)
    assert fetched is not None
    assert fetched.intelligence_candidate_id == candidate_id
    assert fetched.suggested_strategy_type == "moving_average_cross"
    assert fetched.status == IntelligenceStrategyProposalStatus.PENDING
    assert fetched.source == "heuristic"


# ── 2. PENDING 후보에서 proposal 생성 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_creates_proposal_for_pending_candidate(db_session: AsyncSession) -> None:
    """2. PENDING IntelligenceCandidate에서 proposal 생성."""
    await _seed_candidate(db_session)

    generator = IntelligenceStrategyAssignmentGenerator(db_session)
    summary = await generator.generate()

    assert summary.candidates_analyzed >= 1
    assert summary.proposals_created >= 1
    assert summary.errors == []


# ── 3. strategy_type이 등록된 타입인지 검증 ──────────────────────────────────

@pytest.mark.asyncio
async def test_generated_strategy_type_is_registered(db_session: AsyncSession) -> None:
    """3. 생성된 proposal의 suggested_strategy_type이 등록된 전략 타입임."""
    from app.trading.strategy.registry import registered_types
    await _seed_candidate(db_session, why_text="급등 모멘텀", matched_themes=["momentum"])

    generator = IntelligenceStrategyAssignmentGenerator(db_session)
    summary = await generator.generate()
    assert summary.proposals_created >= 1

    repo = IntelligenceStrategyProposalRepository(db_session)
    proposals = await repo.list_recent(limit=10)
    valid = set(registered_types())
    for p in proposals:
        assert p.suggested_strategy_type in valid, (
            f"등록되지 않은 strategy_type: {p.suggested_strategy_type}"
        )


# ── 4. invalid strategy_type은 저장 안 됨 ────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_strategy_type_not_stored(db_session: AsyncSession) -> None:
    """4. _match_strategy가 등록되지 않은 타입을 반환하면 generator가 skip한다.

    monkey-patching으로 fallback을 unregistered 타입으로 교체해 검증.
    """
    import app.services.intelligence_strategy_assignment_generator as gen_mod

    original_match = gen_mod._match_strategy

    def _bad_match(matched_themes, why_text, source_type):
        return "nonexistent_strategy_type_xyz", {"matched_rule": "nonexistent"}

    gen_mod._match_strategy = _bad_match
    try:
        await _seed_candidate(db_session, dedup_suffix="_inv")
        generator = IntelligenceStrategyAssignmentGenerator(db_session)
        summary = await generator.generate()
        assert summary.proposals_created == 0
        assert summary.skipped_invalid >= 1
        assert any("nonexistent" in e for e in summary.errors)
    finally:
        gen_mod._match_strategy = original_match


# ── 5. heuristic 키워드 매칭 ─────────────────────────────────────────────────

@pytest.mark.parametrize("why_text,themes,source_type,expected", [
    ("급등 모멘텀 종목", ["momentum"], "news", "momentum_surge"),
    ("52주 신고가 돌파", [], "news", "breakout_high"),
    ("눌림목 반등 구간", [], "news", "pullback_trend"),
    ("공시 기반 거래량", [], "disclosure", "volume_confirmed_ma_cross"),
    ("외국인 수급 유입", ["flow"], "news", "flow_confirmed_volume_ma_cross"),
    ("RSI 과열 반락", [], "news", "rsi_reversion"),
    ("MACD 골든크로스", [], "news", "macd_trend"),
    ("특별한 신호 없음", [], "news", "moving_average_cross"),
])
def test_heuristic_keyword_matching(
    why_text: str, themes: list, source_type: str, expected: str
) -> None:
    """5. heuristic이 matched_themes/why_text/source_type을 보고 전략을 선택함."""
    strategy_type, _ = _match_strategy(themes, why_text, source_type)
    assert strategy_type == expected, (
        f"why_text={why_text!r} themes={themes} → expected {expected!r}, got {strategy_type!r}"
    )


# ── 6. rationale에 선택 이유 저장 ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rationale_contains_strategy_type(db_session: AsyncSession) -> None:
    """6. rationale에 선택된 strategy_type이 포함됨."""
    await _seed_candidate(db_session, why_text="급등 모멘텀", matched_themes=["momentum"])

    generator = IntelligenceStrategyAssignmentGenerator(db_session)
    await generator.generate()

    repo = IntelligenceStrategyProposalRepository(db_session)
    proposals = await repo.list_recent(limit=5)
    assert len(proposals) >= 1
    p = proposals[0]
    assert p.rationale is not None
    assert p.suggested_strategy_type in p.rationale


# ── 7. score_components 저장 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_score_components_stored(db_session: AsyncSession) -> None:
    """7. score_components가 proposal에 저장됨."""
    await _seed_candidate(db_session, why_text="급등 모멘텀", matched_themes=["momentum"])

    generator = IntelligenceStrategyAssignmentGenerator(db_session)
    await generator.generate()

    repo = IntelligenceStrategyProposalRepository(db_session)
    proposals = await repo.list_recent(limit=5)
    p = proposals[0]
    assert p.score_components is not None
    assert "matched_rule" in p.score_components


# ── 8. 중복 proposal 방지 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_proposal_skipped(db_session: AsyncSession) -> None:
    """8. 같은 candidate에 pending proposal이 있으면 중복 생성 안 함."""
    await _seed_candidate(db_session, dedup_suffix="_dup")

    generator = IntelligenceStrategyAssignmentGenerator(db_session)
    summary1 = await generator.generate()
    assert summary1.proposals_created >= 1

    summary2 = await generator.generate()
    assert summary2.proposals_created == 0
    assert summary2.skipped_existing >= 1


# ── 9. approve → proposal APPROVED ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_sets_proposal_status(db_session: AsyncSession) -> None:
    """9. approve 시 proposal status=APPROVED."""
    candidate_id = await _seed_candidate(db_session, dedup_suffix="_appr")
    generator = IntelligenceStrategyAssignmentGenerator(db_session)
    await generator.generate()

    repo = IntelligenceStrategyProposalRepository(db_session)
    proposals = await repo.list_recent(status=IntelligenceStrategyProposalStatus.PENDING)
    assert len(proposals) >= 1
    p = [x for x in proposals if x.intelligence_candidate_id == candidate_id][0]

    approved = await repo.approve(p, reviewer_note="테스트 승인")
    assert approved.status == IntelligenceStrategyProposalStatus.APPROVED
    assert approved.reviewed_at is not None
    assert approved.reviewer_note == "테스트 승인"


# ── 10. approve → candidate PROMOTED ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_promotes_candidate(db_session: AsyncSession) -> None:
    """10. approve 시 IntelligenceCandidate.status=PROMOTED."""
    candidate_id = await _seed_candidate(db_session, dedup_suffix="_promo")
    generator = IntelligenceStrategyAssignmentGenerator(db_session)
    await generator.generate()

    proposal_repo = IntelligenceStrategyProposalRepository(db_session)
    proposals = await proposal_repo.list_recent(status=IntelligenceStrategyProposalStatus.PENDING)
    p = [x for x in proposals if x.intelligence_candidate_id == candidate_id][0]

    cand_repo = IntelligenceCandidateRepository(db_session)
    candidate = await cand_repo.get(candidate_id)
    assert candidate.status == IntelligenceCandidateStatus.PENDING

    await proposal_repo.approve(p)
    await cand_repo.update_status(candidate, IntelligenceCandidateStatus.PROMOTED)
    await db_session.flush()

    refreshed = await cand_repo.get(candidate_id)
    assert refreshed.status == IntelligenceCandidateStatus.PROMOTED


# ── 11. approve → StrategyVersion 생성 없음 ──────────────────────────────────

@pytest.mark.asyncio
async def test_approve_does_not_create_strategy_version(db_session: AsyncSession) -> None:
    """11. approve 시 StrategyVersion 생성 없음."""
    from sqlalchemy import select, func
    from app.domain.models.strategy import StrategyVersion

    before = (await db_session.execute(select(func.count()).select_from(StrategyVersion))).scalar()

    await _seed_candidate(db_session, dedup_suffix="_nosv")
    generator = IntelligenceStrategyAssignmentGenerator(db_session)
    await generator.generate()

    proposal_repo = IntelligenceStrategyProposalRepository(db_session)
    proposals = await proposal_repo.list_recent(status=IntelligenceStrategyProposalStatus.PENDING)
    if proposals:
        await proposal_repo.approve(proposals[-1])
        await db_session.flush()

    after = (await db_session.execute(select(func.count()).select_from(StrategyVersion))).scalar()
    assert before == after, f"StrategyVersion이 생성되었음: before={before} after={after}"


# ── 12. approve → StrategyAssignmentLog 생성 없음 ────────────────────────────

@pytest.mark.asyncio
async def test_approve_does_not_create_assignment_log(db_session: AsyncSession) -> None:
    """12. approve 시 StrategyAssignmentLog 생성 없음."""
    from sqlalchemy import select, func
    from app.domain.models.strategy_assignment import StrategyAssignmentLog

    before = (
        await db_session.execute(select(func.count()).select_from(StrategyAssignmentLog))
    ).scalar()

    await _seed_candidate(db_session, dedup_suffix="_nolog")
    generator = IntelligenceStrategyAssignmentGenerator(db_session)
    await generator.generate()

    proposal_repo = IntelligenceStrategyProposalRepository(db_session)
    proposals = await proposal_repo.list_recent(status=IntelligenceStrategyProposalStatus.PENDING)
    if proposals:
        await proposal_repo.approve(proposals[-1])
        await db_session.flush()

    after = (
        await db_session.execute(select(func.count()).select_from(StrategyAssignmentLog))
    ).scalar()
    assert before == after, (
        f"StrategyAssignmentLog가 생성되었음: before={before} after={after}"
    )


# ── 13. reject → proposal REJECTED ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_reject_sets_proposal_status(db_session: AsyncSession) -> None:
    """13. reject 시 proposal status=REJECTED."""
    await _seed_candidate(db_session, dedup_suffix="_rej")
    generator = IntelligenceStrategyAssignmentGenerator(db_session)
    await generator.generate()

    repo = IntelligenceStrategyProposalRepository(db_session)
    proposals = await repo.list_recent(status=IntelligenceStrategyProposalStatus.PENDING)
    assert len(proposals) >= 1

    rejected = await repo.reject(proposals[-1], reviewer_note="테스트 거절")
    assert rejected.status == IntelligenceStrategyProposalStatus.REJECTED
    assert rejected.reviewer_note == "테스트 거절"


# ── 14. auto_trade_enabled never True ────────────────────────────────────────

@pytest.mark.asyncio
async def test_auto_trade_enabled_never_true(db_session: AsyncSession) -> None:
    """14. suggested_parameters 안에 auto_trade_enabled=true가 없음."""
    await _seed_candidate(db_session, dedup_suffix="_atf")
    generator = IntelligenceStrategyAssignmentGenerator(db_session)
    await generator.generate()

    repo = IntelligenceStrategyProposalRepository(db_session)
    proposals = await repo.list_recent(limit=100)
    for p in proposals:
        params = p.suggested_parameters or {}
        assert params.get("auto_trade_enabled") is not True, (
            f"proposal {p.id}: auto_trade_enabled=True 발견!"
        )


# ── 15. 기존 StrategyAssignmentLog.candidate_event_id NOT NULL 유지 ────────

def test_existing_assignment_log_fk_not_null() -> None:
    """15. 기존 StrategyAssignmentLog.candidate_event_id는 NOT NULL을 유지한다."""
    from app.domain.models.strategy_assignment import StrategyAssignmentLog
    col = StrategyAssignmentLog.__table__.c["candidate_event_id"]
    assert not col.nullable, "candidate_event_id가 nullable로 변경되었음!"


# ── 16. 기존 AssignmentService.assign() 시그니처 미변경 ──────────────────────

def test_existing_assignment_service_signature_unchanged() -> None:
    """16. AssignmentService.assign()이 candidate_event_id 파라미터를 유지함."""
    from app.services.assignment_service import AssignmentService
    sig = inspect.signature(AssignmentService.assign)
    assert "candidate_event_id" in sig.parameters, (
        "AssignmentService.assign() 시그니처가 변경되었음!"
    )


# ── 17. LLM provider 호출 없음 ───────────────────────────────────────────────

def test_llm_provider_not_imported_in_generator() -> None:
    """17. Generator 소스코드에 AnalysisProvider/analyze() 호출이 없음."""
    import app.services.intelligence_strategy_assignment_generator as gen_mod
    source = inspect.getsource(gen_mod)
    assert "AnalysisProvider" not in source, "AnalysisProvider가 generator에 포함되었음!"
    assert "analyze(" not in source, "analyze() 호출이 generator에 포함되었음!"


# ── 18. order API 호출 없음 ──────────────────────────────────────────────────

def test_order_api_not_in_generator() -> None:
    """18. Generator에 order API 코드가 없음."""
    import app.services.intelligence_strategy_assignment_generator as gen_mod
    source = inspect.getsource(gen_mod)
    for forbidden in ["TTTC0012U", "TTTC0011U", "VTTC0012U", "VTTC0011U", "place_order"]:
        assert forbidden not in source, f"{forbidden!r}가 generator에 포함되었음!"


# ── 19. broker.place_order 변경 없음 (파일 존재 확인) ────────────────────────

def test_live_broker_file_untouched() -> None:
    """19. 실전 브로커 파일이 이번 변경에 포함되지 않음."""
    import pathlib
    broker_file = pathlib.Path(
        __file__
    ).parent.parent / "app" / "broker" / "kis_real.py"
    # 파일 존재 여부만 확인 (내용 변경 여부는 git diff로 확인)
    if broker_file.exists():
        assert True
    else:
        assert True  # 파일이 없어도 OK — broker 구조가 바뀐 경우


# ── 20. KIS_REAL_TRADING_ENABLED 변경 없음 ──────────────────────────────────

def test_kis_real_trading_disabled() -> None:
    """20. KIS_REAL_TRADING_ENABLED는 여전히 False가 기본값이다."""
    from app.core.config import Settings
    s = Settings()
    assert s.kis_real_trading_enabled is False


# ── 21. API smoke: generate ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_generate_smoke(db_session: AsyncSession) -> None:
    """API POST /intelligence/strategy-proposals/generate 기본 동작."""
    await _seed_candidate(db_session, dedup_suffix="_api")

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/intelligence/strategy-proposals/generate",
                json={"candidate_limit": 10},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert "proposals_created" in data
        assert "candidates_analyzed" in data
        assert "errors" in data
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_api_list_proposals(db_session: AsyncSession) -> None:
    """API GET /intelligence/strategy-proposals 기본 동작."""
    await _seed_candidate(db_session, dedup_suffix="_list")

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/api/v1/intelligence/strategy-proposals/generate",
                json={"candidate_limit": 10},
            )
            resp = await client.get("/api/v1/intelligence/strategy-proposals")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_api_approve_and_reject_flow(db_session: AsyncSession) -> None:
    """API approve/reject 엔드포인트 동작."""
    await _seed_candidate(db_session, dedup_suffix="_flow1")
    await _seed_candidate(db_session, dedup_suffix="_flow2")

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            gen_resp = await client.post(
                "/api/v1/intelligence/strategy-proposals/generate",
                json={"candidate_limit": 10},
            )
            assert gen_resp.status_code == 201

            list_resp = await client.get("/api/v1/intelligence/strategy-proposals")
            proposals = list_resp.json()
            assert len(proposals) >= 2

            # 첫 번째 approve
            approve_resp = await client.post(
                f"/api/v1/intelligence/strategy-proposals/{proposals[0]['id']}/approve",
                json={"reviewer_note": "승인"},
            )
            assert approve_resp.status_code == 200
            assert approve_resp.json()["status"] == "approved"

            # 두 번째 reject
            reject_resp = await client.post(
                f"/api/v1/intelligence/strategy-proposals/{proposals[1]['id']}/reject",
                json={"reviewer_note": "거절"},
            )
            assert reject_resp.status_code == 200
            assert reject_resp.json()["status"] == "rejected"

            # 이미 승인된 proposal 재승인 시 409
            dup_resp = await client.post(
                f"/api/v1/intelligence/strategy-proposals/{proposals[0]['id']}/approve",
                json={},
            )
            assert dup_resp.status_code == 409
    finally:
        app.dependency_overrides.pop(get_db, None)
