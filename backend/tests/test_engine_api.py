from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.deps import get_broker_client
from app.main import app
from app.scheduler.lifecycle import ORDER_SYNC_JOB_ID, STRATEGY_RUNNER_JOB_ID
from app.trading.broker.base import BrokerClient
from app.trading.broker.schemas import (
    AccountBalance,
    AccountHolding,
    AccountSummary,
    MinuteCandle,
    OrderExecution,
    OrderRequest,
    OrderResult,
    PriceQuote,
)


class FakeBrokerClient(BrokerClient):
    async def get_current_price(self, symbol_code: str) -> PriceQuote:
        raise NotImplementedError

    async def get_minute_candles(
        self, symbol_code: str, target_time: str | None = None, include_past_data: bool = True
    ) -> list[MinuteCandle]:
        return []

    async def get_account_balance(self) -> AccountBalance:
        return AccountBalance(
            holdings=[],
            summary=AccountSummary(
                total_deposit=Decimal("0"),
                total_purchase_amount=Decimal("0"),
                total_evaluation_amount=Decimal("0"),
                total_profit_loss_amount=Decimal("0"),
            ),
        )

    async def get_account_positions(self) -> list[AccountHolding]:
        return []

    async def place_order(self, order: OrderRequest) -> OrderResult:
        raise NotImplementedError

    async def get_daily_executions(self, target_date: str | None = None) -> list[OrderExecution]:
        return []


async def test_engine_status_and_run_once_and_lifespan() -> None:
    app.dependency_overrides[get_broker_client] = lambda: FakeBrokerClient()

    try:
        with TestClient(app) as client:
            # lifespan에서 scheduler가 시작되고 작업이 등록되어야 한다
            scheduler = app.state.scheduler
            assert scheduler.running is True
            assert any(job.id == STRATEGY_RUNNER_JOB_ID for job in scheduler.get_jobs())

            status_resp = client.get("/api/v1/engine/status")
            assert status_resp.status_code == 200
            status_data = status_resp.json()
            assert status_data["scheduler_running"] is True
            assert STRATEGY_RUNNER_JOB_ID in status_data["registered_jobs"]
            assert ORDER_SYNC_JOB_ID in status_data["registered_jobs"]
            assert "active_strategy_count" in status_data
            assert "last_run_at" in status_data
            assert "last_error" in status_data
            assert "order_sync_last_run_at" in status_data
            assert "order_sync_last_error" in status_data
            assert "recent_run_has_failure" in status_data
            assert "auto_trade_enabled_count" in status_data
            assert status_data["last_error_category"] is None
            assert status_data["order_sync_last_error_category"] is None

            runs_resp = client.get("/api/v1/engine/runs")
            assert runs_resp.status_code == 200
            assert isinstance(runs_resp.json(), list)

            run_resp = client.post("/api/v1/engine/run-once")
            assert run_resp.status_code == 200
            assert run_resp.json() == []

            status_resp_after = client.get("/api/v1/engine/status")
            assert status_resp_after.json()["last_run_at"] is not None

            sync_resp = client.post("/api/v1/engine/sync-orders")
            assert sync_resp.status_code == 200
            sync_data = sync_resp.json()
            assert sync_data == {
                "checked": 0,
                "updated": 0,
                "matched": 0,
                "unmatched": 0,
                "unmatched_order_ids": [],
                "executions": [],
                "errors": [],
                "error_category": None,
                "skipped_reason": "no_pending_orders",
            }

            status_resp_after_sync = client.get("/api/v1/engine/status")
            sync_status_data = status_resp_after_sync.json()
            assert sync_status_data["order_sync_last_run_at"] is not None
            assert sync_status_data["order_sync_last_error"] is None

        # lifespan 종료 시 scheduler가 정상적으로 shutdown 되어야 한다
        assert scheduler.running is False
    finally:
        app.dependency_overrides.clear()


async def test_scheduler_settings_get_and_update() -> None:
    app.dependency_overrides[get_broker_client] = lambda: FakeBrokerClient()

    try:
        with TestClient(app) as client:
            get_resp = client.get("/api/v1/engine/scheduler-settings")
            assert get_resp.status_code == 200
            original = get_resp.json()
            assert original["strategy_scheduler_interval_seconds"] >= 60
            assert original["order_sync_scheduler_interval_seconds"] >= 60

            try:
                # 최소값(60초) 미만은 거부되어야 한다
                invalid_resp = client.patch(
                    "/api/v1/engine/scheduler-settings",
                    json={"strategy_scheduler_interval_seconds": 30},
                )
                assert invalid_resp.status_code == 400

                # 정상 변경은 반영되고, scheduler job이 재스케줄되어야 한다
                update_resp = client.patch(
                    "/api/v1/engine/scheduler-settings",
                    json={"strategy_scheduler_interval_seconds": 120, "order_sync_scheduler_interval_seconds": 90},
                )
                assert update_resp.status_code == 200
                updated = update_resp.json()
                assert updated["strategy_scheduler_interval_seconds"] == 120
                assert updated["order_sync_scheduler_interval_seconds"] == 90

                scheduler = app.state.scheduler
                strategy_job = scheduler.get_job(STRATEGY_RUNNER_JOB_ID)
                order_sync_job = scheduler.get_job(ORDER_SYNC_JOB_ID)
                assert strategy_job.trigger.interval.total_seconds() == 120
                assert order_sync_job.trigger.interval.total_seconds() == 90

                # 새로고침(재조회) 후에도 변경 값이 유지되어야 한다
                get_resp_after = client.get("/api/v1/engine/scheduler-settings")
                assert get_resp_after.json()["strategy_scheduler_interval_seconds"] == 120
                assert get_resp_after.json()["order_sync_scheduler_interval_seconds"] == 90
            finally:
                # 테스트 DB에 영구 반영되므로 원래 값으로 복원한다
                client.patch(
                    "/api/v1/engine/scheduler-settings",
                    json={
                        "strategy_scheduler_interval_seconds": original["strategy_scheduler_interval_seconds"],
                        "order_sync_scheduler_interval_seconds": original["order_sync_scheduler_interval_seconds"],
                    },
                )
    finally:
        app.dependency_overrides.clear()
