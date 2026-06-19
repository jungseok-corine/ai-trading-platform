"""C-2.23 Scanner Rule Foundation 테스트."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.trading.scanner.conditions import (
    InvalidConditionError,
    evaluate_conditions,
    validate_conditions,
)


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


# --- 순수 로직: 조건 검증/평가 -------------------------------------------------
def test_validate_conditions_rejects_empty() -> None:
    with pytest.raises(InvalidConditionError):
        validate_conditions([])


def test_validate_conditions_rejects_bad_params() -> None:
    # validate_conditions가 공개 경계 — Pydantic 검증 에러를 InvalidConditionError로 변환한다.
    with pytest.raises(InvalidConditionError):
        validate_conditions([{"type": "volume_spike", "params": {"multiplier": -1}}])
    with pytest.raises(InvalidConditionError):
        validate_conditions([{"type": "turnover_rank", "params": {}}])
    with pytest.raises(InvalidConditionError):
        validate_conditions([{"type": "investor_flow", "params": {"foreign": "buy"}}])


def test_evaluate_all_conditions_match() -> None:
    conditions = [
        {"type": "volume_spike", "params": {"multiplier": 2.0}},
        {"type": "price_change_pct", "params": {"min_pct": 5.0}},
        {"type": "investor_flow", "params": {"foreign": "net_buy"}},
        {"type": "time_bucket", "params": {"buckets": ["morning"]}},
    ]
    facts = {
        "volume_ratio": 2.1,
        "price_change_pct": 5.3,
        "foreign_flow": "net_buy",
        "time_bucket": "morning",
    }
    result = evaluate_conditions(conditions, facts)
    assert result.matched is True
    assert result.total == 4
    assert result.score == 100


def test_evaluate_partial_match_not_matched() -> None:
    conditions = [
        {"type": "volume_spike", "params": {"multiplier": 2.0}},
        {"type": "price_change_pct", "params": {"min_pct": 5.0}},
    ]
    facts = {"volume_ratio": 2.5, "price_change_pct": 1.0}  # 두번째 미충족
    result = evaluate_conditions(conditions, facts)
    assert result.matched is False
    assert result.matched_conditions == ["volume_spike"]
    assert result.score == 50


def test_evaluate_missing_facts_treated_as_unmatched() -> None:
    conditions = [{"type": "turnover_rank", "params": {"max_rank": 100}}]
    result = evaluate_conditions(conditions, {})  # turnover_rank fact 없음
    assert result.matched is False


# --- API/서비스 ---------------------------------------------------------------
async def test_scanner_rule_full_flow(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            rule_resp = await client.post(
                "/api/v1/scanner-rules",
                json={"name": "장초반 급등주", "market": "KR", "description": "거래량+상승률"},
            )
            assert rule_resp.status_code == 201
            rule = rule_resp.json()
            assert rule["market"] == "KR"
            assert rule["version_count"] == 0
            rule_id = rule["id"]

            ver_resp = await client.post(
                f"/api/v1/scanner-rules/{rule_id}/versions",
                json={
                    "conditions": [
                        {"type": "volume_spike", "params": {"window": 20, "multiplier": 2.0}},
                        {"type": "price_change_pct", "params": {"min_pct": 5.0}},
                    ],
                    "change_description": "초기 버전",
                },
            )
            assert ver_resp.status_code == 201
            version = ver_resp.json()
            assert version["version_no"] == 1
            assert version["status"] == "draft"
            assert len(version["conditions"]) == 2
            version_id = version["id"]

            # 두번째 버전 -> version_no=2
            ver2 = await client.post(
                f"/api/v1/scanner-rules/{rule_id}/versions",
                json={"conditions": [{"type": "turnover_rank", "params": {"max_rank": 50}}]},
            )
            assert ver2.json()["version_no"] == 2

            # evaluate
            eval_resp = await client.post(
                f"/api/v1/scanner-rules/{rule_id}/versions/{version_id}/evaluate",
                json={"facts": {"volume_ratio": 2.4, "price_change_pct": 6.1}},
            )
            assert eval_resp.status_code == 200
            assert eval_resp.json()["matched"] is True
            assert eval_resp.json()["score"] == 100

            # rule 목록 version_count 반영
            rules = await client.get("/api/v1/scanner-rules")
            updated = next(r for r in rules.json() if r["id"] == rule_id)
            assert updated["version_count"] == 2
    finally:
        app.dependency_overrides.clear()


async def test_create_version_invalid_condition_returns_422(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            rule_id = (
                await client.post("/api/v1/scanner-rules", json={"name": "bad"})
            ).json()["id"]

            resp = await client.post(
                f"/api/v1/scanner-rules/{rule_id}/versions",
                json={"conditions": [{"type": "volume_spike", "params": {"multiplier": -1}}]},
            )
            assert resp.status_code == 422

            empty = await client.post(
                f"/api/v1/scanner-rules/{rule_id}/versions",
                json={"conditions": []},
            )
            assert empty.status_code == 422
    finally:
        app.dependency_overrides.clear()


async def test_archived_version_excluded_by_default(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            rule_id = (
                await client.post("/api/v1/scanner-rules", json={"name": "archive test"})
            ).json()["id"]
            version_id = (
                await client.post(
                    f"/api/v1/scanner-rules/{rule_id}/versions",
                    json={"conditions": [{"type": "turnover_rank", "params": {"max_rank": 100}}]},
                )
            ).json()["id"]

            await client.patch(
                f"/api/v1/scanner-rules/{rule_id}/versions/{version_id}",
                json={"status": "archived"},
            )

            default_list = await client.get(f"/api/v1/scanner-rules/{rule_id}/versions")
            assert all(v["id"] != version_id for v in default_list.json())

            with_archived = await client.get(
                f"/api/v1/scanner-rules/{rule_id}/versions",
                params={"include_archived": "true"},
            )
            assert any(v["id"] == version_id for v in with_archived.json())
    finally:
        app.dependency_overrides.clear()
