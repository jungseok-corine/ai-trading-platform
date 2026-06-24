"""C-2.29 Live Promotion Gate 테스트.

검증 항목:
1.  check_readiness — PromotionService.evaluate 결과를 포함한다
2.  기준 통과 시 readiness passed=True
3.  기준 미통과 시 readiness passed=False
4.  confirmed=True 없이 live-promote 호출 → LivePromotionNotConfirmedError(422)
5.  confirmed_by 빈 문자열 → LivePromotionNotConfirmedError(422)
6.  기준 미통과 전략 live-promote → LivePromotionReadinessFailedError(422)
7.  기준 통과 전략 live-promote 성공 → LivePromotionRecord 생성
8.  LivePromotionRecord 생성 확인 (DB 조회)
9.  readiness_snapshot 저장 확인
10. promotion_evaluation_id 연결 확인
11. 이미 approved record가 있으면 중복 승인 거부 (409)
12. StrategyVersion.status는 live-promote 전후 변경되지 않음
13. auto_trade_enabled는 Live promotion 이후 생성되지 않음
14. approved_by 값이 record에 정확히 저장됨
15. note 값이 record에 저장됨
16. 존재하지 않는 strategy_version_id → LivePromotionVersionNotFoundError(404)
17. PromotionCriteria가 없으면 LivePromotionCriteriaNotFoundError(422)
18. check_readiness API GET /live-readiness 정상 응답
19. GET /live-readiness 404 — 존재하지 않는 버전
20. POST /live-promote 성공 응답 (201)
21. POST /live-promote confirmed=False → 422
22. POST /live-promote 중복 → 409
23. POST /live-promote message 안전 문구 확인
24. 기존 PromotionService.evaluate 동작 미변경 확인
25. 금지 심볼 없음 — broker.place_order, TTTC0012U 등
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import MarketCode, StrategyVersionStatus
from app.domain.models.promotion import LivePromotionRecord, PromotionCriteria
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.repositories.promotion import (
    LivePromotionRecordRepository,
    PromotionCriteriaRepository,
    PromotionEvaluationRepository,
)
from app.domain.repositories.strategy import StrategyVersionRepository
from app.main import app
from app.services.live_promotion_gate_service import (
    LivePromotionAlreadyApprovedError,
    LivePromotionCriteriaNotFoundError,
    LivePromotionGateService,
    LivePromotionNotConfirmedError,
    LivePromotionReadinessFailedError,
    LivePromotionVersionNotFoundError,
)
from app.services.promotion_service import PromotionService


# ── 세션 오버라이드 ────────────────────────────────────────────────────────────

def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


# ── 시드 헬퍼 ─────────────────────────────────────────────────────────────────

async def _seed_strategy_version(
    session: AsyncSession,
    name: str = "GateTest",
    status: StrategyVersionStatus = StrategyVersionStatus.DRAFT,
) -> StrategyVersion:
    strategy = Strategy(name=name)
    session.add(strategy)
    await session.flush()
    version = StrategyVersion(
        strategy_id=strategy.id,
        version_no=1,
        parameters={"strategy_type": "momentum_surge", "quantity": 1},
        status=status,
    )
    session.add(version)
    await session.flush()
    return version


async def _seed_criteria(
    session: AsyncSession,
    min_trade_count: int = 0,
    min_days: int = 0,
    min_expectancy: Decimal = Decimal("0"),
    max_drawdown: Decimal | None = None,
) -> PromotionCriteria:
    repo = PromotionCriteriaRepository(session)
    criteria = await repo.create(
        name="TestCriteria",
        market=MarketCode.KR,
        min_trade_count=min_trade_count,
        min_days=min_days,
        min_expectancy=min_expectancy,
        max_drawdown=max_drawdown,
        enabled=True,
    )
    await session.flush()
    return criteria


# ── 테스트 1: check_readiness — PromotionService.evaluate 결과 포함 ─────────────

@pytest.mark.asyncio
async def test_check_readiness_includes_promotion_result(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="ReadinessTest1")
    criteria = await _seed_criteria(db_session)
    await db_session.commit()

    svc = LivePromotionGateService(db_session)
    report = await svc.check_readiness(version.id, criteria_id=criteria.id)

    assert report.strategy_version_id == version.id
    assert report.criteria_id == criteria.id
    assert isinstance(report.trades_count, int)
    assert isinstance(report.days, int)
    assert len(report.checks) > 0


# ── 테스트 2: 기준 통과 (모든 조건 0) ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_readiness_passed_when_criteria_met(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="ReadinessTest2")
    # min=0으로 반드시 통과
    criteria = await _seed_criteria(db_session, min_trade_count=0, min_days=0)
    await db_session.commit()

    svc = LivePromotionGateService(db_session)
    report = await svc.check_readiness(version.id, criteria_id=criteria.id)

    assert report.passed is True


# ── 테스트 3: 기준 미통과 (min_trade_count=9999) ───────────────────────────────

@pytest.mark.asyncio
async def test_check_readiness_failed_when_criteria_not_met(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="ReadinessTest3")
    criteria = await _seed_criteria(db_session, min_trade_count=9999, min_days=9999)
    await db_session.commit()

    svc = LivePromotionGateService(db_session)
    report = await svc.check_readiness(version.id, criteria_id=criteria.id)

    assert report.passed is False
    failed_names = [c["name"] for c in report.checks if not c["passed"]]
    assert "min_trade_count" in failed_names


# ── 테스트 4: confirmed=False → LivePromotionNotConfirmedError ─────────────────

@pytest.mark.asyncio
async def test_approve_requires_confirmed_true(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="ApproveTest4")
    await _seed_criteria(db_session)
    await db_session.commit()

    svc = LivePromotionGateService(db_session)
    with pytest.raises(LivePromotionNotConfirmedError):
        await svc.approve_live_promotion(
            strategy_version_id=version.id,
            confirmed_by="operator",
            confirmed=False,
        )


# ── 테스트 5: confirmed_by 빈 문자열 → LivePromotionNotConfirmedError ──────────

@pytest.mark.asyncio
async def test_approve_requires_non_empty_confirmed_by(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="ApproveTest5")
    await _seed_criteria(db_session)
    await db_session.commit()

    svc = LivePromotionGateService(db_session)
    with pytest.raises(LivePromotionNotConfirmedError):
        await svc.approve_live_promotion(
            strategy_version_id=version.id,
            confirmed_by="   ",
            confirmed=True,
        )


# ── 테스트 6: 기준 미통과 → LivePromotionReadinessFailedError ─────────────────

@pytest.mark.asyncio
async def test_approve_rejects_when_readiness_fails(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="ApproveTest6")
    await _seed_criteria(db_session, min_trade_count=9999)
    await db_session.commit()

    svc = LivePromotionGateService(db_session)
    with pytest.raises(LivePromotionReadinessFailedError) as exc_info:
        await svc.approve_live_promotion(
            strategy_version_id=version.id,
            confirmed_by="operator",
            confirmed=True,
        )
    assert "min_trade_count" in exc_info.value.failed_checks


# ── 테스트 7: 기준 통과 → LivePromotionRecord 생성 성공 ───────────────────────

@pytest.mark.asyncio
async def test_approve_success_creates_record(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="ApproveTest7")
    await _seed_criteria(db_session, min_trade_count=0, min_days=0)
    await db_session.commit()

    svc = LivePromotionGateService(db_session)
    record = await svc.approve_live_promotion(
        strategy_version_id=version.id,
        confirmed_by="test_operator",
        confirmed=True,
    )

    assert record.id is not None
    assert record.strategy_version_id == version.id
    assert record.status == LivePromotionRecord.STATUS_APPROVED
    assert record.criteria_passed is True


# ── 테스트 8: LivePromotionRecord DB 조회 ─────────────────────────────────────

@pytest.mark.asyncio
async def test_live_promotion_record_persisted_in_db(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="ApproveTest8")
    await _seed_criteria(db_session, min_trade_count=0, min_days=0)
    await db_session.commit()

    svc = LivePromotionGateService(db_session)
    record = await svc.approve_live_promotion(
        strategy_version_id=version.id,
        confirmed_by="test_operator",
        confirmed=True,
    )

    repo = LivePromotionRecordRepository(db_session)
    found = await repo.get(record.id)
    assert found is not None
    assert found.strategy_version_id == version.id


# ── 테스트 9: readiness_snapshot 저장 확인 ────────────────────────────────────

@pytest.mark.asyncio
async def test_readiness_snapshot_stored(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="ApproveTest9")
    await _seed_criteria(db_session, min_trade_count=0, min_days=0)
    await db_session.commit()

    svc = LivePromotionGateService(db_session)
    record = await svc.approve_live_promotion(
        strategy_version_id=version.id,
        confirmed_by="test_operator",
        confirmed=True,
    )

    assert record.readiness_snapshot is not None
    assert "strategy_version_id" in record.readiness_snapshot
    assert "passed" in record.readiness_snapshot
    assert "checks" in record.readiness_snapshot


# ── 테스트 10: promotion_evaluation_id 연결 ───────────────────────────────────

@pytest.mark.asyncio
async def test_promotion_evaluation_id_linked(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="ApproveTest10")
    await _seed_criteria(db_session, min_trade_count=0, min_days=0)
    await db_session.commit()

    svc = LivePromotionGateService(db_session)
    record = await svc.approve_live_promotion(
        strategy_version_id=version.id,
        confirmed_by="test_operator",
        confirmed=True,
    )

    assert record.promotion_evaluation_id is not None
    eval_repo = PromotionEvaluationRepository(db_session)
    evals = await eval_repo.list_by_version(version.id)
    assert any(e.id == record.promotion_evaluation_id for e in evals)


# ── 테스트 11: 중복 승인 거부 (409) ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_approval_rejected(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="ApproveTest11")
    await _seed_criteria(db_session, min_trade_count=0, min_days=0)
    await db_session.commit()

    svc = LivePromotionGateService(db_session)
    await svc.approve_live_promotion(
        strategy_version_id=version.id,
        confirmed_by="op1",
        confirmed=True,
    )

    with pytest.raises(LivePromotionAlreadyApprovedError):
        await svc.approve_live_promotion(
            strategy_version_id=version.id,
            confirmed_by="op2",
            confirmed=True,
        )


# ── 테스트 12: StrategyVersion.status 변경되지 않음 ───────────────────────────

@pytest.mark.asyncio
async def test_strategy_version_status_unchanged(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(
        db_session, name="ApproveTest12", status=StrategyVersionStatus.DRAFT
    )
    original_status = version.status
    await _seed_criteria(db_session, min_trade_count=0, min_days=0)
    await db_session.commit()

    svc = LivePromotionGateService(db_session)
    await svc.approve_live_promotion(
        strategy_version_id=version.id,
        confirmed_by="test_operator",
        confirmed=True,
    )

    # DB에서 다시 로드하여 확인
    version_repo = StrategyVersionRepository(db_session)
    refreshed = await version_repo.get(version.id)
    assert refreshed is not None
    assert refreshed.status == original_status


# ── 테스트 13: auto_trade_enabled 변경 없음 ───────────────────────────────────

@pytest.mark.asyncio
async def test_auto_trade_enabled_not_changed(db_session: AsyncSession) -> None:
    """LivePromotionRecord, readiness_snapshot 어디에도 auto_trade_enabled=true가 없어야 한다."""
    version = await _seed_strategy_version(db_session, name="ApproveTest13")
    await _seed_criteria(db_session, min_trade_count=0, min_days=0)
    await db_session.commit()

    svc = LivePromotionGateService(db_session)
    record = await svc.approve_live_promotion(
        strategy_version_id=version.id,
        confirmed_by="test_operator",
        confirmed=True,
    )

    # readiness_snapshot에 auto_trade_enabled=true 없음
    if record.readiness_snapshot:
        snapshot_str = str(record.readiness_snapshot)
        assert "auto_trade_enabled" not in snapshot_str.lower()

    # risk_snapshot에도 없음
    if record.risk_snapshot:
        assert "auto_trade_enabled" not in str(record.risk_snapshot).lower()


# ── 테스트 14: approved_by 정확히 저장 ────────────────────────────────────────

@pytest.mark.asyncio
async def test_approved_by_stored_correctly(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="ApproveTest14")
    await _seed_criteria(db_session, min_trade_count=0, min_days=0)
    await db_session.commit()

    svc = LivePromotionGateService(db_session)
    record = await svc.approve_live_promotion(
        strategy_version_id=version.id,
        confirmed_by="  human_reviewer  ",
        note="looks good",
        confirmed=True,
    )

    assert record.approved_by == "human_reviewer"


# ── 테스트 15: note 저장 확인 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_note_stored(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="ApproveTest15")
    await _seed_criteria(db_session, min_trade_count=0, min_days=0)
    await db_session.commit()

    svc = LivePromotionGateService(db_session)
    record = await svc.approve_live_promotion(
        strategy_version_id=version.id,
        confirmed_by="op",
        note="승격 이유: 30일 운용 결과 양호",
        confirmed=True,
    )

    assert record.note == "승격 이유: 30일 운용 결과 양호"


# ── 테스트 16: 존재하지 않는 버전 → LivePromotionVersionNotFoundError ──────────

@pytest.mark.asyncio
async def test_missing_version_raises_error(db_session: AsyncSession) -> None:
    await _seed_criteria(db_session)
    await db_session.commit()

    svc = LivePromotionGateService(db_session)
    with pytest.raises(LivePromotionVersionNotFoundError):
        await svc.check_readiness(999_999_999)


# ── 테스트 17: PromotionCriteria 없음 → LivePromotionCriteriaNotFoundError ─────

@pytest.mark.asyncio
async def test_no_criteria_raises_error(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="NoCriteriaTest")
    await db_session.commit()

    svc = LivePromotionGateService(db_session)
    with pytest.raises(LivePromotionCriteriaNotFoundError):
        await svc.check_readiness(version.id)


# ── 테스트 18: API GET /live-readiness 정상 ──────────────────────────────────

@pytest.mark.asyncio
async def test_api_get_live_readiness(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="APITest18")
    criteria = await _seed_criteria(db_session, min_trade_count=0, min_days=0)
    await db_session.commit()

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/strategy-versions/{version.id}/live-readiness",
                params={"criteria_id": criteria.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["strategy_version_id"] == version.id
        assert "passed" in data
        assert "checks" in data
    finally:
        app.dependency_overrides.pop(get_db, None)


# ── 테스트 19: API GET /live-readiness 404 ────────────────────────────────────

@pytest.mark.asyncio
async def test_api_get_live_readiness_version_not_found(db_session: AsyncSession) -> None:
    await _seed_criteria(db_session)
    await db_session.commit()

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/strategy-versions/999999/live-readiness")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


# ── 테스트 20: API POST /live-promote 성공 (201) ──────────────────────────────

@pytest.mark.asyncio
async def test_api_post_live_promote_success(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="APITest20")
    criteria = await _seed_criteria(db_session, min_trade_count=0, min_days=0)
    await db_session.commit()

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/v1/strategy-versions/{version.id}/live-promote",
                params={"criteria_id": criteria.id},
                json={"confirmed": True, "confirmed_by": "human_op", "note": "ok"},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["record"]["strategy_version_id"] == version.id
        assert data["record"]["status"] == "approved"
        assert data["record"]["criteria_passed"] is True
    finally:
        app.dependency_overrides.pop(get_db, None)


# ── 테스트 21: API POST confirmed=False → 422 ────────────────────────────────

@pytest.mark.asyncio
async def test_api_post_live_promote_confirmed_false_422(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="APITest21")
    await _seed_criteria(db_session, min_trade_count=0, min_days=0)
    await db_session.commit()

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/v1/strategy-versions/{version.id}/live-promote",
                json={"confirmed": False, "confirmed_by": "op"},
            )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_db, None)


# ── 테스트 22: API POST 중복 승인 → 409 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_api_post_live_promote_duplicate_409(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="APITest22")
    criteria = await _seed_criteria(db_session, min_trade_count=0, min_days=0)
    await db_session.commit()

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post(
                f"/api/v1/strategy-versions/{version.id}/live-promote",
                params={"criteria_id": criteria.id},
                json={"confirmed": True, "confirmed_by": "op1"},
            )
            resp2 = await client.post(
                f"/api/v1/strategy-versions/{version.id}/live-promote",
                params={"criteria_id": criteria.id},
                json={"confirmed": True, "confirmed_by": "op2"},
            )
        assert resp2.status_code == 409
    finally:
        app.dependency_overrides.pop(get_db, None)


# ── 테스트 23: API 응답에 안전 문구 포함 ─────────────────────────────────────

@pytest.mark.asyncio
async def test_api_post_live_promote_message_contains_safety_notice(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="APITest23")
    criteria = await _seed_criteria(db_session, min_trade_count=0, min_days=0)
    await db_session.commit()

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/v1/strategy-versions/{version.id}/live-promote",
                params={"criteria_id": criteria.id},
                json={"confirmed": True, "confirmed_by": "op"},
            )
        data = resp.json()
        assert "Real trading remains disabled" in data["message"]
    finally:
        app.dependency_overrides.pop(get_db, None)


# ── 테스트 24: 기존 PromotionService.evaluate 동작 미변경 ──────────────────────

@pytest.mark.asyncio
async def test_existing_promotion_service_unaffected(db_session: AsyncSession) -> None:
    version = await _seed_strategy_version(db_session, name="CompatTest24")
    criteria = await _seed_criteria(db_session, min_trade_count=0, min_days=0)
    await db_session.commit()

    svc = PromotionService(db_session)
    result = await svc.evaluate(version.id, criteria.id, persist=False)

    assert result.strategy_version_id == version.id
    assert result.criteria_id == criteria.id
    assert isinstance(result.passed, bool)


# ── 테스트 25: 금지 심볼 없음 ─────────────────────────────────────────────────

def test_no_forbidden_symbols_in_service() -> None:
    """live_promotion_gate_service.py에 실전 주문 금지 심볼이 없어야 한다."""
    import app.services.live_promotion_gate_service as mod

    src = inspect.getsource(mod)
    forbidden = [
        "TTTC0012U",
        "TTTC0011U",
        "VTTC0012U",
        "VTTC0011U",
        "broker.place_order",
        "KIS_REAL_TRADING_ENABLED",
    ]
    for sym in forbidden:
        assert sym not in src, f"금지 심볼 발견: {sym}"


def test_no_forbidden_symbols_in_api() -> None:
    """live_promotion.py API에 실전 주문 금지 심볼이 없어야 한다."""
    import app.api.v1.live_promotion as mod

    src = inspect.getsource(mod)
    forbidden = [
        "TTTC0012U",
        "TTTC0011U",
        "VTTC0012U",
        "VTTC0011U",
        "broker.place_order",
        "auto_trade_enabled",
    ]
    for sym in forbidden:
        assert sym not in src, f"금지 심볼 발견: {sym}"
