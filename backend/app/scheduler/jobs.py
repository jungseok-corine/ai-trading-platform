import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from app.db.session import async_session_factory
from app.domain.models.enums import SchedulerRunStatus
from app.services.market_data_service import MarketDataService
from app.services.order_sync_service import OrderSyncService
from app.services.risk_service import RiskService
from app.services.scheduler_run_service import SchedulerRunService
from app.services.signal_service import SignalService
from app.services.strategy_runner_service import StrategyRunnerService
from app.services.trade_service import TradeService
from app.trading.broker.error_classifier import classify_exception, exc_message

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

STRATEGY_RUNNER_JOB_ID = "strategy_runner"
ORDER_SYNC_JOB_ID = "order_sync"


async def _record_run(
    job_id: str,
    started_at: datetime,
    finished_at: datetime,
    status: SchedulerRunStatus,
    error_message: str | None,
    summary: dict,
) -> None:
    """scheduler_runs에 실행 결과를 기록한다. 기록 자체의 실패가 scheduler를 죽이면 안 된다."""
    try:
        async with async_session_factory() as session:
            await SchedulerRunService(session).record_run(
                job_id=job_id,
                started_at=started_at,
                finished_at=finished_at,
                status=status,
                error_message=error_message,
                summary=summary,
            )
    except Exception:  # noqa: BLE001 - 로그 기록 실패가 scheduler를 죽이면 안 됨
        logger.exception("failed to record scheduler_runs row for job_id=%s", job_id)


async def run_strategy_job(app: FastAPI) -> None:
    """활성 전략을 1회 실행하고 Signal이 생성되면 signal_logs에 저장한다.

    parameters.auto_trade_enabled=true인 전략에 한해 RiskManager 검증 후 자동 주문까지
    시도한다. 실행 결과(시각/에러)는 app.state와 scheduler_runs 테이블에 기록되어
    /api/v1/engine/status, /api/v1/engine/runs 에서 조회할 수 있다.
    """
    started_at = datetime.now(KST)
    status = SchedulerRunStatus.SUCCESS
    error_message: str | None = None
    summary: dict = {}

    try:
        async with async_session_factory() as session:
            broker = app.state.broker_client
            signal_service = SignalService(session, MarketDataService(broker))
            risk_service = RiskService(session, broker)
            trade_service = TradeService(session, broker, risk_service)
            runner = StrategyRunnerService(session, signal_service, trade_service)
            results = await runner.run_once()

        signals_created = sum(1 for r in results if r.signal_created)
        trades_attempted = sum(1 for r in results if r.trade_attempted)
        versions_failed = sum(1 for r in results if r.error)
        versions_succeeded = len(results) - versions_failed
        failed_symbols = [r.symbol_code for r in results if r.error]
        error_categories = list({r.error_category for r in results if r.error_category})
        errors = [
            {
                "strategy_version_id": r.strategy_version_id,
                "symbol_code": r.symbol_code,
                "message": r.error,
                "category": r.error_category,
            }
            for r in results
            if r.error
        ]
        summary = {
            "versions_run": len(results),
            "versions_succeeded": versions_succeeded,
            "versions_failed": versions_failed,
            "failed_symbols": failed_symbols,
            "signals_created": signals_created,
            "trades_attempted": trades_attempted,
            "error_categories": error_categories,
            "errors": errors,
        }

        if signals_created or trades_attempted:
            logger.info(
                "strategy scheduler: %d signal(s) generated, %d trade(s) attempted",
                signals_created, trades_attempted,
            )

        if versions_failed:
            logger.warning(
                "strategy scheduler: %d/%d version(s) failed — symbols: %s",
                versions_failed, len(results), failed_symbols,
            )

        # Status 정책:
        # - FAILED: job 자체가 crash하거나 모든 version이 실패한 경우
        # - SKIPPED: 실행할 전략이 없음
        # - SUCCESS: 일부라도 성공하면 SUCCESS (per-symbol 오류는 summary에 기록)
        if errors and versions_succeeded == 0:
            status = SchedulerRunStatus.FAILED
            error_message = "; ".join(e["message"] for e in errors)
        elif not results:
            status = SchedulerRunStatus.SKIPPED

        app.state.scheduler_last_error = error_message
        app.state.scheduler_last_error_category = error_categories[0] if error_categories else None
    except Exception as exc:  # noqa: BLE001 - 스케줄러는 예외로 죽으면 안 됨
        logger.exception("strategy scheduler job failed")
        status = SchedulerRunStatus.FAILED
        error_message = exc_message(exc)
        error_category = classify_exception(exc)
        summary = {"errors": [{"strategy_version_id": None, "symbol_code": None, "message": error_message, "category": error_category}]}
        app.state.scheduler_last_error = error_message
        app.state.scheduler_last_error_category = error_category
    finally:
        finished_at = datetime.now(KST)
        app.state.scheduler_last_run_at = finished_at
        await _record_run(STRATEGY_RUNNER_JOB_ID, started_at, finished_at, status, error_message, summary)


async def order_sync_job(app: FastAPI) -> None:
    """pending/partial 상태인 주문의 체결 여부를 KIS 주문체결조회 API로 동기화한다.

    실행 결과(시각/에러)는 app.state와 scheduler_runs 테이블에 기록되어
    /api/v1/engine/status, /api/v1/engine/runs 에서 조회할 수 있다.
    """
    started_at = datetime.now(KST)
    status = SchedulerRunStatus.SUCCESS
    error_message: str | None = None
    summary: dict = {}

    try:
        async with async_session_factory() as session:
            broker = app.state.broker_client
            sync_service = OrderSyncService(session, broker)
            result = await sync_service.sync_pending_orders()

        errors = [{"strategy_version_id": None, "symbol_code": None, "message": e, "category": result.error_category} for e in result.errors]
        summary = {
            "checked": result.checked,
            "matched": result.matched,
            "unmatched": result.unmatched,
            "updated": result.updated,
            "stale_cancelled": result.stale_cancelled,
            "stale_pending_requires_review": result.stale_pending_requires_review,
            "unmatched_order_ids": result.unmatched_order_ids,
            "executions": result.executions,
            "errors": errors,
            "error_category": result.error_category,
            "skipped_reason": result.skipped_reason,
        }

        if result.updated or result.errors:
            logger.info(
                "order sync: %d/%d trade(s) updated, %d error(s), stale_cancelled=%d, requires_review=%d",
                result.updated, result.checked, len(result.errors),
                result.stale_cancelled, result.stale_pending_requires_review,
            )

        # Status 정책:
        # - FAILED: KIS API 자체 조회 실패 (error_category 설정됨)
        # - SKIPPED: pending 주문 없음
        # - SUCCESS: API 성공 (per-trade 오류는 summary.errors에 기록)
        if result.error_category:
            status = SchedulerRunStatus.FAILED
            error_message = "; ".join(result.errors)
        elif result.skipped_reason:
            status = SchedulerRunStatus.SKIPPED

        app.state.order_sync_last_error = error_message
        app.state.order_sync_last_error_category = result.error_category
    except Exception as exc:  # noqa: BLE001 - 스케줄러는 예외로 죽으면 안 됨
        logger.exception("order sync job failed")
        status = SchedulerRunStatus.FAILED
        error_message = exc_message(exc)
        error_category = classify_exception(exc)
        summary = {"errors": [{"strategy_version_id": None, "symbol_code": None, "message": error_message, "category": error_category}]}
        app.state.order_sync_last_error = error_message
        app.state.order_sync_last_error_category = error_category
    finally:
        finished_at = datetime.now(KST)
        app.state.order_sync_last_run_at = finished_at
        await _record_run(ORDER_SYNC_JOB_ID, started_at, finished_at, status, error_message, summary)
