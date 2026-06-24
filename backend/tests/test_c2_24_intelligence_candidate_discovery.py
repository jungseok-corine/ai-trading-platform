"""C-2.24 Intelligence Candidate Discovery System 테스트.

검증 항목:
1.  IntelligenceCandidate 생성/조회
2.  dedup_hash unique 제약
3.  symbol_code가 있는 event에서 후보 생성
4.  symbol_code가 없는 event는 skip
5.  score가 0~100으로 clamp
6.  score_components 저장
7.  why_text가 deterministic하게 생성
8.  theme synergy bonus가 score에 반영
9.  중복 후보는 skip
10. POST /intelligence/discover summary 반환
11. GET /intelligence/candidates 필터 동작
12. scheduler 기본 비활성
13. 기존 CandidateEvent.scanner_rule_version_id nullable 변경 없음
14. CandidateEvent.score 직접 수정 없음
15. LLM provider 호출 없음
16. 주문 API 호출 없음
17. broker.place_order 변경 없음
18. KIS_REAL_TRADING_ENABLED 변경 없음
"""
from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.domain.models.enums import (
    IntelligenceCandidateStatus,
    IntelligenceEventStatus,
    IntelligenceMarketScope,
    IntelligenceProvider,
    IntelligenceSourceType,
    MarketCode,
)
from app.domain.repositories.intelligence import (
    IntelligenceEventRepository,
    IntelligenceSourceRepository,
)
from app.domain.repositories.intelligence_candidate import IntelligenceCandidateRepository
from app.domain.repositories.market_context import ThemeRepository, SymbolThemeMembershipRepository
from app.services.intelligence_candidate_discovery_service import (
    IntelligenceCandidateDiscoveryService,
)


# ── 공통 시드 헬퍼 ────────────────────────────────────────────────────────────

async def _seed_source(session: AsyncSession, source_key: str = "test_src") -> int:
    repo = IntelligenceSourceRepository(session)
    src = await repo.create(
        source_key=source_key,
        source_type=IntelligenceSourceType.NEWS,
        provider=IntelligenceProvider.RSS,
        market_scope=IntelligenceMarketScope.KR,
        enabled=True,
        config={},
    )
    await session.flush()
    return src.id


async def _seed_event(
    session: AsyncSession,
    source_id: int,
    symbol_code: str | None = "005930",
    title: str = "삼성전자 반도체 투자 확대",
    dedup_hash: str = "evt_hash_001",
    importance_score: float | None = 0.8,
    event_type: str = "news",
) -> int:
    repo = IntelligenceEventRepository(session)
    event = await repo.create(
        source_id=source_id,
        event_type=event_type,
        market=MarketCode.KR,
        symbol_code=symbol_code,
        title=title,
        importance_score=importance_score,
        dedup_hash=dedup_hash,
        status=IntelligenceEventStatus.RAW,
    )
    await session.flush()
    return event.id


# ── 1. IntelligenceCandidate 생성/조회 ────────────────────────────────────────

async def test_intelligence_candidate_create_and_get(db_session: AsyncSession) -> None:
    """IntelligenceCandidate를 생성하고 ID로 조회할 수 있다."""
    repo = IntelligenceCandidateRepository(db_session)
    candidate = await repo.create(
        symbol_code="005930",
        market=MarketCode.KR,
        score=75,
        why_text="뉴스 이벤트 '삼성전자 반도체 투자 확대'에 의해 후보로 생성됨. importance_score=80.",
        status=IntelligenceCandidateStatus.PENDING,
        source_type="news",
        matched_themes=["semiconductor"],
        score_components={"base_importance": 80, "final_score": 75},
        dedup_hash="cand_hash_test_001",
    )
    await db_session.flush()

    fetched = await repo.get(candidate.id)
    assert fetched is not None
    assert fetched.symbol_code == "005930"
    assert fetched.score == 75
    assert fetched.status == IntelligenceCandidateStatus.PENDING
    assert fetched.matched_themes == ["semiconductor"]


# ── 2. dedup_hash unique 제약 ─────────────────────────────────────────────────

async def test_intelligence_candidate_dedup_hash_unique(db_session: AsyncSession) -> None:
    """동일 dedup_hash로 두 번 생성하면 UniqueConstraint가 발생한다."""
    from sqlalchemy.exc import IntegrityError

    repo = IntelligenceCandidateRepository(db_session)
    await repo.create(
        symbol_code="005930",
        market=MarketCode.KR,
        score=50,
        status=IntelligenceCandidateStatus.PENDING,
        dedup_hash="dup_hash_test",
    )
    await db_session.flush()

    with pytest.raises(IntegrityError):
        await repo.create(
            symbol_code="005930",
            market=MarketCode.KR,
            score=60,
            status=IntelligenceCandidateStatus.PENDING,
            dedup_hash="dup_hash_test",
        )
        await db_session.flush()


# ── 3. symbol_code가 있는 event에서 후보 생성 ─────────────────────────────────

async def test_discover_creates_candidate_for_event_with_symbol(
    db_session: AsyncSession,
) -> None:
    """symbol_code가 있는 IntelligenceEvent에서 IntelligenceCandidate가 생성된다."""
    src_id = await _seed_source(db_session, "src_sym_001")
    await _seed_event(db_session, src_id, symbol_code="005930", dedup_hash="sym_event_001")
    await db_session.flush()

    svc = IntelligenceCandidateDiscoveryService(db_session)
    summary = await svc.discover(lookback_hours=24)

    assert summary.events_checked >= 1
    assert summary.candidates_created >= 1
    assert summary.skipped_no_symbol_count == 0

    repo = IntelligenceCandidateRepository(db_session)
    candidates = await repo.list_recent(symbol_code="005930")
    assert any(c.symbol_code == "005930" for c in candidates)


# ── 4. symbol_code가 없는 event는 skip ────────────────────────────────────────

async def test_discover_skips_event_without_symbol(db_session: AsyncSession) -> None:
    """symbol_code가 None인 이벤트는 후보화하지 않고 skipped_no_symbol_count에 집계된다."""
    src_id = await _seed_source(db_session, "src_no_sym_001")
    await _seed_event(db_session, src_id, symbol_code=None, dedup_hash="no_sym_event_001")
    await db_session.flush()

    svc = IntelligenceCandidateDiscoveryService(db_session)
    summary = await svc.discover(lookback_hours=24)

    assert summary.skipped_no_symbol_count >= 1
    # symbol_code가 없으므로 후보 생성 0
    assert summary.candidates_created == 0


# ── 5. score가 0~100으로 clamp ─────────────────────────────────────────────────

def test_score_clamp_to_100() -> None:
    """score는 100을 초과하지 않는다."""
    from app.domain.models.intelligence import IntelligenceEvent
    from decimal import Decimal

    evt = MagicMock(spec=IntelligenceEvent)
    evt.importance_score = Decimal("1.000")  # base = 100
    evt.event_type = "disclosure"            # source_bonus = 5
    evt.collected_at = None                  # age_hours = 24 → recency_bonus = 0

    # symbol_themes와 active_themes에 10개 교집합 → theme_bonus = 100
    symbol_themes = [f"t{i}" for i in range(10)]
    active_themes = [f"t{i}" for i in range(10)]

    score, components = IntelligenceCandidateDiscoveryService._calc_score(
        evt, symbol_themes, active_themes
    )
    assert score == 100
    assert components["final_score"] == 100


def test_score_clamp_to_zero() -> None:
    """score는 0 미만이 되지 않는다 (모든 구성 요소가 0이면 최솟값 0)."""
    from app.domain.models.intelligence import IntelligenceEvent
    from decimal import Decimal

    evt = MagicMock(spec=IntelligenceEvent)
    evt.importance_score = Decimal("0.000")
    evt.event_type = "news"
    evt.collected_at = None

    score, components = IntelligenceCandidateDiscoveryService._calc_score(evt, [], [])
    assert score >= 0
    assert components["final_score"] >= 0


# ── 6. score_components 저장 ─────────────────────────────────────────────────

async def test_discover_saves_score_components(db_session: AsyncSession) -> None:
    """생성된 후보의 score_components에 계산 근거가 저장된다."""
    src_id = await _seed_source(db_session, "src_comp_001")
    await _seed_event(
        db_session, src_id,
        symbol_code="035420",
        dedup_hash="comp_event_001",
        importance_score=0.7,
    )
    await db_session.flush()

    svc = IntelligenceCandidateDiscoveryService(db_session)
    await svc.discover(lookback_hours=24)

    repo = IntelligenceCandidateRepository(db_session)
    candidates = await repo.list_recent(symbol_code="035420")
    assert candidates
    comp = candidates[0].score_components
    assert comp is not None
    assert "base_importance" in comp
    assert "theme_bonus" in comp
    assert "recency_bonus" in comp
    assert "source_bonus" in comp
    assert "final_score" in comp


# ── 7. why_text가 deterministic하게 생성 ─────────────────────────────────────

def test_why_text_is_deterministic() -> None:
    """동일 입력에 항상 동일 why_text가 생성된다 (LLM 미사용, template 기반)."""
    from app.domain.models.intelligence import IntelligenceEvent

    evt = MagicMock(spec=IntelligenceEvent)
    evt.title = "삼성전자 HBM 공급 확대"
    evt.event_type = "news"

    components = {"base_importance": 80, "theme_bonus": 10, "recency_bonus": 5, "source_bonus": 3}
    matched_themes = ["semiconductor", "hbm"]

    text1 = IntelligenceCandidateDiscoveryService._build_why_text(evt, matched_themes, components)
    text2 = IntelligenceCandidateDiscoveryService._build_why_text(evt, matched_themes, components)
    assert text1 == text2
    assert "삼성전자 HBM 공급 확대" in text1
    assert "semiconductor" in text1 or "hbm" in text1
    assert "importance_score=80" in text1


def test_why_text_no_themes() -> None:
    """matched_themes가 없으면 테마 언급 없이 why_text가 생성된다."""
    from app.domain.models.intelligence import IntelligenceEvent

    evt = MagicMock(spec=IntelligenceEvent)
    evt.title = "시장 동향 기사"
    evt.event_type = "news"

    components = {"base_importance": 50, "theme_bonus": 0, "recency_bonus": 8, "source_bonus": 3}
    text = IntelligenceCandidateDiscoveryService._build_why_text(evt, [], components)
    assert "시장 동향 기사" in text
    assert "importance_score=50" in text


# ── 8. theme synergy bonus가 score에 반영 ────────────────────────────────────

async def test_theme_synergy_reflected_in_score(db_session: AsyncSession) -> None:
    """symbol이 활성 테마와 연결되면 score_components.theme_bonus > 0이다."""
    theme_repo = ThemeRepository(db_session)
    membership_repo = SymbolThemeMembershipRepository(db_session)
    src_id = await _seed_source(db_session, "src_theme_001")
    evt_id = await _seed_event(
        db_session, src_id, symbol_code="000660", dedup_hash="theme_event_001"
    )
    await db_session.flush()

    theme = await theme_repo.create(MarketCode.KR, "semiconductor", "반도체")
    await db_session.flush()
    await membership_repo.create(MarketCode.KR, "000660", theme.id)
    await db_session.flush()

    # intelligence event에 "반도체" 언급 → ThemeActivityService가 탐지
    evt_repo = IntelligenceEventRepository(db_session)
    evt2_id = await evt_repo.create(
        source_id=src_id,
        event_type="news",
        market=MarketCode.KR,
        symbol_code="000660",
        title="SK하이닉스 반도체 실적 호조",
        dedup_hash="theme_event_002",
        status=IntelligenceEventStatus.RAW,
    )
    await db_session.flush()

    svc = IntelligenceCandidateDiscoveryService(db_session)
    await svc.discover(lookback_hours=24)

    repo = IntelligenceCandidateRepository(db_session)
    candidates = await repo.list_recent(symbol_code="000660")
    assert candidates
    # 최소 하나는 theme_bonus > 0 이어야 함
    assert any(
        (c.score_components or {}).get("theme_bonus", 0) > 0
        for c in candidates
    )


# ── 9. 중복 후보는 skip ───────────────────────────────────────────────────────

async def test_discover_skips_duplicate_candidate(db_session: AsyncSession) -> None:
    """동일 IntelligenceEvent에서 두 번 discover를 실행해도 후보가 1개만 생성된다."""
    src_id = await _seed_source(db_session, "src_dup_001")
    await _seed_event(db_session, src_id, symbol_code="051910", dedup_hash="dup_cand_event_001")
    await db_session.flush()

    svc = IntelligenceCandidateDiscoveryService(db_session)
    summary1 = await svc.discover(lookback_hours=24)
    summary2 = await svc.discover(lookback_hours=24)

    assert summary1.candidates_created >= 1
    assert summary2.candidates_created == 0
    assert summary2.skipped_duplicate_count >= 1

    repo = IntelligenceCandidateRepository(db_session)
    candidates = await repo.list_recent(symbol_code="051910")
    assert len(candidates) == 1


# ── 10. POST /intelligence/discover summary 반환 ─────────────────────────────

def test_api_discover_returns_summary() -> None:
    """POST /api/v1/intelligence/discover가 DiscoverySummary를 반환한다."""
    from app.main import app

    with TestClient(app) as client:
        resp = client.post("/api/v1/intelligence/discover", json={})

    assert resp.status_code == 201
    body = resp.json()
    assert "events_checked" in body
    assert "candidates_created" in body
    assert "skipped_duplicate_count" in body
    assert "skipped_no_symbol_count" in body
    assert "errors" in body
    assert isinstance(body["errors"], list)


# ── 11. GET /intelligence/candidates 필터 동작 ───────────────────────────────

def test_api_list_candidates_returns_list() -> None:
    """GET /api/v1/intelligence/candidates가 list를 반환한다."""
    from app.main import app

    with TestClient(app) as client:
        resp = client.get("/api/v1/intelligence/candidates")

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_api_list_candidates_status_filter() -> None:
    """GET /api/v1/intelligence/candidates?status=pending이 동작한다."""
    from app.main import app

    with TestClient(app) as client:
        resp = client.get("/api/v1/intelligence/candidates?status=pending")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    for item in body:
        assert item["status"] == "pending"


# ── 12. scheduler 기본 비활성 ─────────────────────────────────────────────────

def test_intelligence_discovery_scheduler_default_disabled() -> None:
    """intelligence_discovery_scheduler_enabled 기본값이 False다."""
    s = Settings(_env_file=None)
    assert s.intelligence_discovery_scheduler_enabled is False


def test_intelligence_discovery_scheduler_in_registry() -> None:
    """INTELLIGENCE_DISCOVERY_JOB_ID가 CONTROLLABLE_JOBS에 등록돼 있고 기본 비활성이다."""
    from app.scheduler.jobs import INTELLIGENCE_DISCOVERY_JOB_ID
    from app.scheduler.registry import CONTROLLABLE_BY_ID

    assert INTELLIGENCE_DISCOVERY_JOB_ID in CONTROLLABLE_BY_ID
    job = CONTROLLABLE_BY_ID[INTELLIGENCE_DISCOVERY_JOB_ID]
    s = Settings(_env_file=None)
    assert job.env_enabled(s) is False


# ── 13. 기존 CandidateEvent.scanner_rule_version_id nullable 변경 없음 ────────

def test_candidate_event_scanner_rule_version_id_is_not_nullable() -> None:
    """기존 CandidateEvent.scanner_rule_version_id는 NOT NULL로 유지된다."""
    from sqlalchemy import inspect as sa_inspect

    from app.domain.models.candidate_event import CandidateEvent

    mapper = sa_inspect(CandidateEvent)
    col = mapper.columns["scanner_rule_version_id"]
    assert col.nullable is False, "scanner_rule_version_id must remain NOT NULL"


# ── 14. CandidateEvent.score 직접 수정 없음 ──────────────────────────────────

def test_discovery_service_does_not_touch_candidate_event_score() -> None:
    """IntelligenceCandidateDiscoveryService 소스코드에 CandidateEvent가 임포트되지 않는다."""
    import pathlib

    source = (
        pathlib.Path(__file__).parent.parent
        / "app" / "services" / "intelligence_candidate_discovery_service.py"
    ).read_text()
    assert "CandidateEvent" not in source
    assert "candidate_event" not in source


# ── 15. LLM provider 호출 없음 ────────────────────────────────────────────────

def test_no_llm_provider_in_discovery_service() -> None:
    """discovery service에 AnalysisProvider / LLM 관련 심볼이 없다."""
    import pathlib

    llm_symbols = {"AnalysisProvider", "analyze(", "get_analysis_provider"}
    source = (
        pathlib.Path(__file__).parent.parent
        / "app" / "services" / "intelligence_candidate_discovery_service.py"
    ).read_text()
    for sym in llm_symbols:
        assert sym not in source, f"LLM 심볼 '{sym}'이 discovery service에서 발견됨"


# ── 16–18. 안전 불변식 ────────────────────────────────────────────────────────

def test_no_order_api_in_discovery_service() -> None:
    """discovery service에 주문 API 심볼이 없다."""
    import pathlib

    order_symbols = {"place_order", "TTTC0012U", "TTTC0011U", "VTTC0012U", "VTTC0011U"}
    source = (
        pathlib.Path(__file__).parent.parent
        / "app" / "services" / "intelligence_candidate_discovery_service.py"
    ).read_text()
    for sym in order_symbols:
        assert sym not in source, f"주문 API 심볼 '{sym}'이 discovery service에서 발견됨"


def test_no_broker_place_order_in_intelligence_api() -> None:
    """intelligence.py API에 broker.place_order가 없다."""
    import pathlib

    source = (
        pathlib.Path(__file__).parent.parent / "app" / "api" / "v1" / "intelligence.py"
    ).read_text()
    assert "place_order" not in source


def test_real_trading_unchanged() -> None:
    """KIS_REAL_TRADING_ENABLED 기본값이 False로 유지된다."""
    s = Settings(_env_file=None)
    assert s.kis_real_trading_enabled is False
