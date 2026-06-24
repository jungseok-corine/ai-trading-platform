"""C-2.23 Market/Theme Context Foundation 테스트.

검증 항목:
1. build_full()이 themes 키를 포함한다
2. build_full()이 recent_intelligence 키를 포함한다
3. recent_intelligence는 limit 설정대로 제한된다
4. ThemeActivityService가 이벤트 타이틀에서 활성 테마를 탐지한다
5. ThemeActivityService가 Theme.code/name 문자열로 매칭한다
6. ThemeSynergyScorer가 공통 테마 수 × bonus를 반환한다
7. ThemeSynergyScorer가 공통 테마가 없으면 0을 반환한다
8. MarketContextSnapshot.data JSONB에 theme_snapshot을 저장/조회한다
9. CandidateEvent.score를 수정하지 않는다
10. 주문 API 호출 없음
11. broker.place_order 변경 없음
12. KIS_REAL_TRADING_ENABLED 변경 없음
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.domain.models.enums import (
    IntelligenceEventStatus,
    IntelligenceMarketScope,
    IntelligenceProvider,
    IntelligenceSourceType,
    MarketCode,
)
from app.domain.models.market_context import MarketContextSnapshot, SymbolThemeMembership, Theme
from app.domain.repositories.intelligence import (
    IntelligenceEventRepository,
    IntelligenceSourceRepository,
)
from app.domain.repositories.market_context import (
    MarketContextSnapshotRepository,
    SymbolThemeMembershipRepository,
    ThemeRepository,
)
from app.services.analysis_bundle_service import AnalysisBundleService
from app.services.strategy_service import StrategyService
from app.services.theme_activity_service import (
    ThemeActivityService,
    compute_theme_synergy_bonus,
)


# ── 공통 시드 헬퍼 ────────────────────────────────────────────────────────────

async def _seed_strategy(session: AsyncSession, symbol_code: str = "005930") -> int:
    """최소 StrategyVersion을 생성하고 version.id를 반환한다."""
    svc = StrategyService(session)
    strategy = await svc.create_strategy("theme-test-strat")
    version = await svc.create_version(strategy.id, parameters={"symbol_code": symbol_code})
    await session.flush()
    return version.id


async def _seed_intelligence_source(session: AsyncSession) -> int:
    src_repo = IntelligenceSourceRepository(session)
    src = await src_repo.create(
        source_key="test_rss_theme",
        source_type=IntelligenceSourceType.NEWS,
        provider=IntelligenceProvider.RSS,
        market_scope=IntelligenceMarketScope.KR,
        enabled=True,
        config={"feed_url": "https://example.com/rss"},
    )
    await session.flush()
    return src.id


# ── 1. build_full()이 themes 키를 포함 ────────────────────────────────────────

async def test_build_full_includes_themes_key(db_session: AsyncSession) -> None:
    """build_full() 결과에 'themes' 키가 존재하고 list다."""
    vid = await _seed_strategy(db_session)
    bundle = await AnalysisBundleService(db_session).build_full(
        vid, datetime.now(timezone.utc).date()
    )
    assert bundle is not None
    assert "themes" in bundle
    assert isinstance(bundle["themes"], list)


# ── 2. build_full()이 recent_intelligence 키를 포함 ──────────────────────────

async def test_build_full_includes_recent_intelligence_key(db_session: AsyncSession) -> None:
    """build_full() 결과에 'recent_intelligence' 키가 존재하고 list다."""
    vid = await _seed_strategy(db_session)
    bundle = await AnalysisBundleService(db_session).build_full(
        vid, datetime.now(timezone.utc).date()
    )
    assert bundle is not None
    assert "recent_intelligence" in bundle
    assert isinstance(bundle["recent_intelligence"], list)


# ── 3. recent_intelligence limit 제한 ────────────────────────────────────────

async def test_recent_intelligence_respects_limit(db_session: AsyncSession) -> None:
    """list_recent_for_bundle은 limit=10으로 제한된다."""
    evt_repo = IntelligenceEventRepository(db_session)
    src_id = await _seed_intelligence_source(db_session)

    # 12개 이벤트 삽입
    for i in range(12):
        await evt_repo.create(
            source_id=src_id,
            event_type="news",
            market=MarketCode.KR,
            symbol_code="005930",
            title=f"뉴스 {i}",
            dedup_hash=f"hash_limit_test_{i}",
            status=IntelligenceEventStatus.RAW,
        )
    await db_session.flush()

    result = await evt_repo.list_recent_for_bundle(
        hours=24, market=MarketCode.KR, symbol_code="005930", limit=10
    )
    assert len(result) <= 10


# ── 4. ThemeActivityService — 이벤트 타이틀에서 활성 테마 탐지 ───────────────

async def test_theme_activity_detects_active_theme_from_title(
    db_session: AsyncSession,
) -> None:
    """이벤트 title에 테마 code/name이 포함되면 active_themes에 등록된다."""
    theme_repo = ThemeRepository(db_session)
    evt_repo = IntelligenceEventRepository(db_session)
    src_id = await _seed_intelligence_source(db_session)

    # 반도체 테마 생성
    await theme_repo.create(MarketCode.KR, "semiconductor", "반도체")
    await db_session.flush()

    # "반도체" 포함 이벤트 삽입
    await evt_repo.create(
        source_id=src_id,
        event_type="news",
        market=MarketCode.KR,
        title="삼성전자 반도체 라인 증설 발표",
        dedup_hash="hash_theme_test_1",
        status=IntelligenceEventStatus.RAW,
    )
    await db_session.flush()

    svc = ThemeActivityService(db_session)
    result = await svc.get_active_themes(MarketCode.KR, lookback_hours=24)

    assert "semiconductor" in result["active_themes"]
    assert result["hot_count"] >= 1
    assert result["matched_events"] >= 1
    assert result["lookback_hours"] == 24


# ── 5. ThemeActivityService — Theme.code / name 모두 매칭 ────────────────────

async def test_theme_activity_matches_code_and_name(db_session: AsyncSession) -> None:
    """테마 code가 이벤트에 등장하면 code로, name이 등장하면 name으로 탐지한다."""
    theme_repo = ThemeRepository(db_session)
    evt_repo = IntelligenceEventRepository(db_session)
    src_id = await _seed_intelligence_source(db_session)

    await theme_repo.create(MarketCode.KR, "ai", "인공지능")
    await db_session.flush()

    # code("ai")가 포함된 이벤트
    await evt_repo.create(
        source_id=src_id,
        event_type="news",
        market=MarketCode.KR,
        title="AI 투자 급증 보고서",
        dedup_hash="hash_code_match",
        status=IntelligenceEventStatus.RAW,
    )
    # name("인공지능")이 포함된 이벤트
    await evt_repo.create(
        source_id=src_id,
        event_type="news",
        market=MarketCode.KR,
        title="인공지능 스타트업 투자 증가",
        dedup_hash="hash_name_match",
        status=IntelligenceEventStatus.RAW,
    )
    await db_session.flush()

    svc = ThemeActivityService(db_session)
    result = await svc.get_active_themes(MarketCode.KR, lookback_hours=24)

    assert "ai" in result["active_themes"]
    # 두 이벤트 모두 매칭
    assert result["matched_events"] >= 2


# ── 6. ThemeSynergyScorer — 공통 테마 bonus 반환 ─────────────────────────────

def test_theme_synergy_bonus_for_common_themes() -> None:
    """symbol_themes ∩ active_themes 개수 × bonus_per_theme를 반환한다."""
    bonus = compute_theme_synergy_bonus(
        symbol_themes=["semiconductor", "ai", "battery"],
        active_themes=["ai", "semiconductor", "bio"],
        bonus_per_theme=10,
    )
    assert bonus == 20  # 공통: ai, semiconductor → 2 × 10


# ── 7. ThemeSynergyScorer — 공통 테마 없음 → 0 ───────────────────────────────

def test_theme_synergy_bonus_zero_when_no_common() -> None:
    """공통 테마가 없으면 0을 반환한다."""
    bonus = compute_theme_synergy_bonus(
        symbol_themes=["battery"],
        active_themes=["bio", "platform"],
    )
    assert bonus == 0


# ── 8. MarketContextSnapshot.data JSONB에 theme_snapshot 저장/조회 ────────────

async def test_market_context_snapshot_stores_theme_snapshot(
    db_session: AsyncSession,
) -> None:
    """MarketContextSnapshot.data JSONB에 theme_snapshot을 저장하고 조회할 수 있다."""
    repo = MarketContextSnapshotRepository(db_session)
    theme_snapshot = {
        "active_themes": ["semiconductor", "ai"],
        "hot_count": 2,
        "lookback_hours": 24,
    }
    snapshot = await repo.create(
        market=MarketCode.KR,
        data={"theme_snapshot": theme_snapshot},
    )
    await db_session.flush()

    fetched = await repo.get(snapshot.id)
    assert fetched is not None
    assert fetched.data is not None
    ts = fetched.data["theme_snapshot"]
    assert ts["hot_count"] == 2
    assert "semiconductor" in ts["active_themes"]


# ── 9. CandidateEvent.score를 수정하지 않음 ──────────────────────────────────

def test_candidate_event_score_not_modified_by_theme_scorer() -> None:
    """compute_theme_synergy_bonus는 순수 함수 — CandidateEvent를 전달받지 않는다."""
    import inspect

    from app.services.theme_activity_service import compute_theme_synergy_bonus

    sig = inspect.signature(compute_theme_synergy_bonus)
    param_names = list(sig.parameters.keys())
    # CandidateEvent 또는 score를 파라미터로 받지 않는다
    assert "candidate" not in param_names
    assert "score" not in param_names
    assert "event" not in param_names


# ── 10–12. 안전 불변식 ────────────────────────────────────────────────────────

def test_no_order_api_in_theme_activity_service() -> None:
    """theme_activity_service.py에 주문 API 심볼이 없다."""
    import pathlib

    order_symbols = {"place_order", "TTTC0012U", "TTTC0011U", "VTTC0012U", "VTTC0011U"}
    target = (
        pathlib.Path(__file__).parent.parent
        / "app"
        / "services"
        / "theme_activity_service.py"
    )
    source = target.read_text()
    for sym in order_symbols:
        assert sym not in source, (
            f"주문 API 심볼 '{sym}'이 theme_activity_service.py에서 발견됨"
        )


def test_no_broker_place_order_in_analysis_bundle() -> None:
    """analysis_bundle_service.py에 broker.place_order가 없다."""
    import pathlib

    target = (
        pathlib.Path(__file__).parent.parent
        / "app"
        / "services"
        / "analysis_bundle_service.py"
    )
    source = target.read_text()
    assert "place_order" not in source, (
        "analysis_bundle_service.py에 place_order 호출이 발견됨"
    )


def test_real_trading_unchanged() -> None:
    """KIS_REAL_TRADING_ENABLED 기본값이 False로 유지된다."""
    s = Settings(_env_file=None)
    assert s.kis_real_trading_enabled is False
