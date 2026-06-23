"""C-2.21.1b Market Intelligence Adapter Foundation 테스트.

검증 항목:
- IntelligenceSource 생성 및 source_key 유니크 제약
- IntelligenceEvent 생성 및 dedup_hash 유니크 제약
- IntelligenceEvent가 IntelligenceSource에 연결됨
- 어댑터 base DTO가 정규화 원본 항목을 올바르게 표현
- build_dedup_hash 결정론적 동작
- 주문 API 호출 없음
- KIS 주문 브로커 호출 없음
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import (
    IntelligenceEventStatus,
    IntelligenceMarketScope,
    IntelligenceProvider,
    IntelligenceSourceType,
    MarketCode,
)
from app.domain.models.intelligence import IntelligenceEvent, IntelligenceSource
from app.domain.repositories.intelligence import (
    IntelligenceEventRepository,
    IntelligenceSourceRepository,
)
from app.market_intelligence.adapters.base import (
    IntelligenceAdapter,
    IntelligenceEventCandidate,
    IntelligenceRawItem,
    build_dedup_hash,
)
from app.market_intelligence.adapters.dart_finance_adapter import DartFinanceAdapter


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _make_source(**overrides) -> dict:
    base = dict(
        source_key="test_source",
        source_type=IntelligenceSourceType.DISCLOSURE,
        provider=IntelligenceProvider.DART,
        market_scope=IntelligenceMarketScope.KR,
        enabled=True,
    )
    base.update(overrides)
    return base


def _make_event(source_id: int, dedup_hash: str = "abc123", **overrides) -> dict:
    base = dict(
        source_id=source_id,
        event_type="disclosure",
        title="테스트 공시",
        dedup_hash=dedup_hash,
        status=IntelligenceEventStatus.RAW,
    )
    base.update(overrides)
    return base


# ── IntelligenceSource 테스트 ─────────────────────────────────────────────────

async def test_create_intelligence_source(db_session: AsyncSession) -> None:
    repo = IntelligenceSourceRepository(db_session)
    src = await repo.create(**_make_source())
    await db_session.flush()

    assert src.id is not None
    assert src.source_key == "test_source"
    assert src.source_type == IntelligenceSourceType.DISCLOSURE
    assert src.provider == IntelligenceProvider.DART
    assert src.market_scope == IntelligenceMarketScope.KR
    assert src.enabled is True


async def test_source_key_uniqueness(db_session: AsyncSession) -> None:
    """동일 source_key로 두 번 생성하면 IntegrityError가 발생한다."""
    repo = IntelligenceSourceRepository(db_session)
    await repo.create(**_make_source(source_key="unique_key"))
    await db_session.flush()

    with pytest.raises(IntegrityError):
        await repo.create(**_make_source(source_key="unique_key"))
        await db_session.flush()


async def test_get_source_by_key(db_session: AsyncSession) -> None:
    repo = IntelligenceSourceRepository(db_session)
    await repo.create(**_make_source(source_key="lookup_key"))
    await db_session.flush()

    found = await repo.get_by_key("lookup_key")
    assert found is not None
    assert found.source_key == "lookup_key"

    not_found = await repo.get_by_key("no_such_key")
    assert not_found is None


async def test_list_enabled_sources(db_session: AsyncSession) -> None:
    repo = IntelligenceSourceRepository(db_session)
    await repo.create(**_make_source(source_key="enabled_src", enabled=True))
    await repo.create(**_make_source(source_key="disabled_src", enabled=False))
    await db_session.flush()

    enabled = await repo.list_enabled()
    keys = [s.source_key for s in enabled]
    assert "enabled_src" in keys
    assert "disabled_src" not in keys


async def test_source_optional_fields(db_session: AsyncSession) -> None:
    """reliability_score와 config는 nullable이다."""
    repo = IntelligenceSourceRepository(db_session)
    src = await repo.create(**_make_source(reliability_score=None, config=None))
    await db_session.flush()
    assert src.reliability_score is None
    assert src.config is None

    src2 = await repo.create(**_make_source(
        source_key="with_config",
        reliability_score=0.85,
        config={"endpoint": "https://example.com"},
    ))
    await db_session.flush()
    assert float(src2.reliability_score) == pytest.approx(0.85, abs=0.001)
    assert src2.config["endpoint"] == "https://example.com"


# ── IntelligenceEvent 테스트 ──────────────────────────────────────────────────

async def test_create_intelligence_event(db_session: AsyncSession) -> None:
    src_repo = IntelligenceSourceRepository(db_session)
    src = await src_repo.create(**_make_source())
    await db_session.flush()

    evt_repo = IntelligenceEventRepository(db_session)
    evt = await evt_repo.create(**_make_event(src.id, dedup_hash="hash_001"))
    await db_session.flush()

    assert evt.id is not None
    assert evt.source_id == src.id
    assert evt.dedup_hash == "hash_001"
    assert evt.status == IntelligenceEventStatus.RAW


async def test_event_dedup_hash_uniqueness(db_session: AsyncSession) -> None:
    """동일 dedup_hash로 두 번 생성하면 IntegrityError가 발생한다."""
    src_repo = IntelligenceSourceRepository(db_session)
    src = await src_repo.create(**_make_source())
    await db_session.flush()

    evt_repo = IntelligenceEventRepository(db_session)
    await evt_repo.create(**_make_event(src.id, dedup_hash="dup_hash"))
    await db_session.flush()

    with pytest.raises(IntegrityError):
        await evt_repo.create(**_make_event(src.id, dedup_hash="dup_hash"))
        await db_session.flush()


async def test_event_linked_to_source(db_session: AsyncSession) -> None:
    """IntelligenceEvent.source_id가 IntelligenceSource를 올바르게 참조한다."""
    src_repo = IntelligenceSourceRepository(db_session)
    src = await src_repo.create(**_make_source(source_key="link_test"))
    await db_session.flush()

    evt_repo = IntelligenceEventRepository(db_session)
    evt = await evt_repo.create(**_make_event(src.id, dedup_hash="link_hash"))
    await db_session.flush()

    assert evt.source_id == src.id

    # FK 참조 확인: source로 조회
    events = await evt_repo.list_by_source(src.id)
    assert any(e.dedup_hash == "link_hash" for e in events)


async def test_event_invalid_source_id_raises(db_session: AsyncSession) -> None:
    """존재하지 않는 source_id로 이벤트 생성하면 IntegrityError가 발생한다."""
    evt_repo = IntelligenceEventRepository(db_session)
    with pytest.raises(IntegrityError):
        await evt_repo.create(**_make_event(source_id=99999, dedup_hash="orphan_hash"))
        await db_session.flush()


async def test_existing_hashes(db_session: AsyncSession) -> None:
    """existing_hashes()가 이미 저장된 해시만 반환한다."""
    src_repo = IntelligenceSourceRepository(db_session)
    src = await src_repo.create(**_make_source())
    await db_session.flush()

    evt_repo = IntelligenceEventRepository(db_session)
    await evt_repo.create(**_make_event(src.id, dedup_hash="exist_hash_1"))
    await evt_repo.create(**_make_event(src.id, dedup_hash="exist_hash_2"))
    await db_session.flush()

    existing = await evt_repo.existing_hashes(
        ["exist_hash_1", "exist_hash_2", "new_hash_3"]
    )
    assert existing == {"exist_hash_1", "exist_hash_2"}
    assert "new_hash_3" not in existing


# ── 어댑터 base DTO 테스트 ────────────────────────────────────────────────────

def test_intelligence_raw_item_fields() -> None:
    """IntelligenceRawItem이 필수 필드를 올바르게 담는다."""
    raw = IntelligenceRawItem(
        raw_id="dart-005930-2023",
        title="삼성전자 2023 사업보고서",
        raw_data={"corp_code": "00126380", "bsns_year": "2023"},
        symbol_code="005930",
        source_ref="https://dart.fss.or.kr/...",
    )
    assert raw.raw_id == "dart-005930-2023"
    assert raw.symbol_code == "005930"
    assert raw.raw_data["corp_code"] == "00126380"


def test_intelligence_event_candidate_fields() -> None:
    """IntelligenceEventCandidate가 필수 필드와 선택 필드를 올바르게 담는다."""
    candidate = IntelligenceEventCandidate(
        source_key="dart_finance",
        event_type="financials_annual",
        title="삼성전자 2023 연간 재무제표",
        dedup_hash="abc123def456",
        market=MarketCode.KR,
        symbol_code="005930",
        status=IntelligenceEventStatus.NORMALIZED,
    )
    assert candidate.source_key == "dart_finance"
    assert candidate.event_type == "financials_annual"
    assert candidate.market == MarketCode.KR
    assert candidate.status == IntelligenceEventStatus.NORMALIZED


def test_build_dedup_hash_deterministic() -> None:
    """동일 입력은 항상 동일 hash를 반환한다."""
    h1 = build_dedup_hash("dart_finance", "005930", "2023", "11011", "CFS")
    h2 = build_dedup_hash("dart_finance", "005930", "2023", "11011", "CFS")
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_build_dedup_hash_different_inputs_differ() -> None:
    """다른 입력은 다른 hash를 반환한다."""
    h1 = build_dedup_hash("dart_finance", "005930", "2023", "11011", "CFS")
    h2 = build_dedup_hash("dart_finance", "005930", "2023", "11011", "OFS")
    assert h1 != h2


def test_intelligence_adapter_is_abstract() -> None:
    """IntelligenceAdapter는 직접 인스턴스화할 수 없다."""
    with pytest.raises(TypeError):
        IntelligenceAdapter()  # type: ignore[abstract]


# ── DartFinanceAdapter 스켈레톤 테스트 ───────────────────────────────────────

def test_dart_finance_adapter_metadata() -> None:
    """DartFinanceAdapter의 source_key / source_type / provider가 올바르게 정의됐다."""
    assert DartFinanceAdapter.source_key == "dart_finance"
    assert DartFinanceAdapter.source_type == IntelligenceSourceType.FINANCIALS
    assert DartFinanceAdapter.provider == IntelligenceProvider.DART
    assert DartFinanceAdapter.market_scope == IntelligenceMarketScope.KR


def test_dart_finance_adapter_fetch_raises_not_implemented() -> None:
    """DartFinanceAdapter.fetch()는 아직 미구현 상태임을 명시한다."""
    import asyncio
    adapter = DartFinanceAdapter()
    with pytest.raises(NotImplementedError):
        asyncio.run(adapter.fetch())


def test_dart_finance_adapter_normalize_returns_candidate() -> None:
    """DartFinanceAdapter.normalize()가 IntelligenceEventCandidate를 반환한다."""
    adapter = DartFinanceAdapter()
    raw = IntelligenceRawItem(
        raw_id="00126380-2023-11011-CFS",
        title="삼성전자",
        raw_data={
            "corp_code": "00126380",
            "bsns_year": "2023",
            "reprt_code": "11011",
            "fs_div": "CFS",
        },
        symbol_code="005930",
    )
    candidate = adapter.normalize(raw)
    assert isinstance(candidate, IntelligenceEventCandidate)
    assert candidate.event_type == "financials_annual"
    assert candidate.symbol_code == "005930"
    assert len(candidate.dedup_hash) == 64


# ── 안전 불변식 검증 ──────────────────────────────────────────────────────────

def test_no_order_api_imports_in_intelligence_modules() -> None:
    """market_intelligence 패키지가 주문 API 관련 심볼을 import하지 않는다."""
    import ast
    import pathlib

    mi_root = pathlib.Path(__file__).parent.parent / "app" / "market_intelligence"
    order_symbols = {"place_order", "TTTC0012U", "TTTC0011U", "VTTC0012U", "VTTC0011U"}

    for py_file in mi_root.rglob("*.py"):
        source = py_file.read_text()
        for sym in order_symbols:
            assert sym not in source, (
                f"주문 API 심볼 '{sym}'이 {py_file}에서 발견됨 — 안전 불변식 위반"
            )
