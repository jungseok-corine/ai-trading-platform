import logging
from datetime import datetime
from app.common.timezone import KST

from fastapi import FastAPI

from app.db.session import async_session_factory
from app.domain.models.enums import SchedulerRunStatus
from app.domain.repositories.investor_flow import InvestorFlowRepository
from app.services.market_data_service import MarketDataService
from app.services.order_sync_service import OrderSyncService
from app.services.risk_service import RiskService
from app.services.scheduler_run_service import SchedulerRunService
from app.services.signal_service import SignalService
from app.services.strategy_runner_service import StrategyRunnerService
from app.services.trade_service import TradeService
from app.services.trading_state_sync_service import TradingStateSyncService
from app.trading.broker.error_classifier import (
    classify_exception,
    exc_message,
    is_transient_error,
)

logger = logging.getLogger(__name__)


STRATEGY_RUNNER_JOB_ID = "strategy_runner"
ORDER_SYNC_JOB_ID = "order_sync"
TRADING_STATE_SYNC_JOB_ID = "trading_state_sync"
DAILY_REPORT_JOB_ID = "daily_report"
DATA_REFRESH_JOB_ID = "data_refresh"
RESEARCH_PIPELINE_JOB_ID = "research_pipeline"
SCANNER_REVIEW_JOB_ID = "scanner_review"
STRATEGY_REVIEW_JOB_ID = "strategy_review"
US_MARKET_REFRESH_JOB_ID = "us_market_refresh"
DAILY_ANALYSIS_JOB_ID = "daily_analysis"
DART_INGEST_JOB_ID = "dart_ingest"
OPERATIONS_DIGEST_JOB_ID = "operations_digest"


async def run_dart_ingest_job(app: FastAPI) -> None:
    """장중 보유/관심 종목의 중요 공시를 DART에서 가져와 저장한다 (C-2.59).

    중요도 미달 공시는 거른다. read-only 수집으로 주문과 무관하다.
    """
    from app.services.dart_ingest_service import DartIngestService

    try:
        async with async_session_factory() as session:
            summary = await DartIngestService(session).ingest()
        logger.info(
            "dart ingest: fetched=%s matched=%s material=%s created=%s",
            summary.fetched, summary.matched, summary.material, summary.created,
        )
        app.state.dart_ingest_last_run_at = datetime.now(KST)
    except Exception as exc:  # noqa: BLE001 - 수집 실패가 스케줄러를 중단시키지 않도록
        logger.error("dart ingest job failed: %s", exc_message(exc))
        app.state.dart_ingest_last_error = exc_message(exc)


INTRADAY_EVENT_MONITOR_JOB_ID = "intraday_event_monitor"


async def run_intraday_event_monitor_job(app: FastAPI) -> None:
    """§7.1 보유/활성 종목 한정 장중 공시 감시. 장 마감 후/주말엔 건너뛴다.

    범위를 좁혀(보유 포지션 + 활성 단일종목 전략) 비용·노이즈를 줄인다. read-only.
    """
    from app.common.market_session import MarketPhase, kr_market_phase
    from app.core.config import get_settings
    from app.services.intraday_event_monitor_service import IntradayEventMonitorService

    # 장중(+장전/장후 NXT 시간대)만 폴링 — 주말/심야 불필요 호출 차단.
    if kr_market_phase(datetime.now(KST)) == MarketPhase.CLOSED:
        app.state.intraday_event_monitor_last_run_at = datetime.now(KST)
        return

    try:
        settings = get_settings()
        async with async_session_factory() as session:
            result = await IntradayEventMonitorService(session).run_once(
                min_score=settings.intraday_event_monitor_min_score
            )
        logger.info(
            "intraday event monitor: monitored=%s material=%s created=%s",
            result.get("monitored"), result.get("material"), result.get("created"),
        )
        app.state.intraday_event_monitor_last_run_at = datetime.now(KST)
    except Exception as exc:  # noqa: BLE001 - 감시 실패가 스케줄러를 중단시키지 않도록
        logger.error("intraday event monitor job failed: %s", exc_message(exc))
        app.state.intraday_event_monitor_last_error = exc_message(exc)


async def run_operations_digest_job(app: FastAPI) -> None:
    """운영 다이제스트를 만들어 설정된 알림 채널로 보낸다 (C-3.9).

    조치 항목이 없으면 전송을 건너뛴다. 채널 기본값은 none(no-op)이라 기본 상태에선
    외부로 아무것도 보내지 않는다. read-only 집계 + (선택) 알림 — 주문과 무관하다.
    """
    from app.core.config import get_settings
    from app.services.notifications import get_notification_channel
    from app.services.operations_digest_service import OperationsDigestService
    from app.services.operations_snapshot_service import OperationsSnapshotService

    try:
        settings = get_settings()
        async with async_session_factory() as session:
            digest = await OperationsDigestService(session).build(
                days=settings.operations_digest_window_days
            )
            text = OperationsDigestService(session).render_text(digest)
            # 추세용 일자 스냅샷도 함께 적재(멱등). read-only 집계의 적재.
            await OperationsSnapshotService(session).record(
                days=settings.operations_digest_window_days
            )
            await session.commit()
        sent = False
        if digest["has_alerts"]:
            channel = get_notification_channel(settings.notification_provider)
            result = await channel.send("운영 다이제스트", text)
            sent = result.sent
        logger.info(
            "operations digest: severity=%s alerts=%s sent=%s",
            digest["severity"], len(digest["alerts"]), sent,
        )
        app.state.operations_digest_last_run_at = datetime.now(KST)
    except Exception as exc:  # noqa: BLE001 - 다이제스트 실패가 스케줄러를 중단시키지 않도록
        logger.error("operations digest job failed: %s", exc_message(exc))
        app.state.operations_digest_last_error = exc_message(exc)


async def run_daily_analysis_job(app: FastAPI) -> None:
    """장마감 후 활성 전략 버전을 활동량 게이트로 선별해 LLM 분석한다 (C-2.54).

    provider/model/mode는 설정에서 읽으며 기본은 fake. 분석은 read-only 메타 작업이다.
    """
    from app.services.daily_analysis_service import DailyAnalysisService

    try:
        async with async_session_factory() as session:
            summary = await DailyAnalysisService(session).run_and_record()
        logger.info(
            "daily analysis: versions=%s analyzed=%s skipped=%s mode=%s",
            summary.versions, summary.analyzed, summary.skipped, summary.mode,
        )
        app.state.daily_analysis_last_run_at = datetime.now(KST)
    except Exception as exc:  # noqa: BLE001 - 분석 실패가 스케줄러를 중단시키지 않도록
        logger.error("daily analysis job failed: %s", exc_message(exc))
        app.state.daily_analysis_last_error = exc_message(exc)


async def run_us_market_refresh_job(app: FastAPI) -> None:
    """설정된 provider에서 미국장 일별 스냅샷을 가져와 upsert한다 (C-2.44).

    기본 provider("manual")는 외부 호출 없이 no-op이다. read-only 수집으로 주문과 무관하다.
    """
    from app.services.us_market_refresh_service import UsMarketRefreshService

    try:
        async with async_session_factory() as session:
            result = await UsMarketRefreshService(session).refresh()
        logger.info(
            "us market refresh: provider=%s updated=%s", result.provider, result.updated
        )
        app.state.us_market_refresh_last_run_at = datetime.now(KST)
    except Exception as exc:  # noqa: BLE001 - 수집 실패가 스케줄러를 중단시키지 않도록
        logger.error("us market refresh job failed: %s", exc_message(exc))
        app.state.us_market_refresh_last_error = exc_message(exc)


async def run_strategy_review_job(app: FastAPI) -> None:
    """active/testing 전략 버전을 점검해 파라미터 조정 제안(pending)을 생성한다 (C-2.42).

    거래 성과 분석만 사용하는 메타 작업으로 주문/외부 API 호출이 없다.
    """
    from app.services.strategy_review_service import StrategyReviewService

    try:
        async with async_session_factory() as session:
            summary = await StrategyReviewService(session).review_and_record()
        logger.info(
            "strategy review: versions=%s proposals=%s skipped=%s",
            summary.versions_reviewed, summary.proposals_created, summary.skipped_existing,
        )
        app.state.strategy_review_last_run_at = datetime.now(KST)
    except Exception as exc:  # noqa: BLE001 - 점검 실패가 스케줄러를 중단시키지 않도록
        logger.error("strategy review job failed: %s", exc_message(exc))
        app.state.strategy_review_last_error = exc_message(exc)


async def run_scanner_review_job(app: FastAPI) -> None:
    """active/testing 스캐너 버전을 점검해 조건 강화 제안(pending)을 생성한다 (C-2.40).

    후보 성과 분석만 사용하는 메타 작업으로 주문/외부 API 호출이 없다.
    """
    from app.core.config import get_settings
    from app.services.scanner_review_service import ScannerReviewService

    settings = get_settings()
    try:
        async with async_session_factory() as session:
            summary = await ScannerReviewService(session).review_and_record(
                horizon_minutes=settings.scanner_review_horizon_minutes
            )
        logger.info(
            "scanner review: versions=%s proposals=%s skipped=%s",
            summary.versions_reviewed, summary.proposals_created, summary.skipped_existing,
        )
        app.state.scanner_review_last_run_at = datetime.now(KST)
    except Exception as exc:  # noqa: BLE001 - 점검 실패가 스케줄러를 중단시키지 않도록
        logger.error("scanner review job failed: %s", exc_message(exc))
        app.state.scanner_review_last_error = exc_message(exc)


async def run_research_pipeline_job(app: FastAPI) -> None:
    """스캔 → 후보 발견 → 전략 배정을 1회 자동 실행한다 (C-2.35).

    DB의 시장/수급 데이터만 사용하며 주문은 발생하지 않는다.
    """
    from app.services.research_pipeline_service import ResearchPipelineService

    try:
        async with async_session_factory() as session:
            summary = await ResearchPipelineService(session).run_and_record()
        logger.info(
            "research pipeline: versions=%s symbols=%s candidates=%s assignments=%s",
            summary.versions, summary.symbols, summary.candidates, summary.assignments,
        )
        app.state.research_pipeline_last_run_at = datetime.now(KST)
    except Exception as exc:  # noqa: BLE001 - 파이프라인 실패가 스케줄러를 중단시키지 않도록
        logger.error("research pipeline job failed: %s", exc_message(exc))
        app.state.research_pipeline_last_error = exc_message(exc)


async def run_data_refresh_job(app: FastAPI) -> None:
    """watchlist 종목의 수급 데이터를 KIS에서 가져와 DB에 채운다 (C-2.34).

    read-only 시세/수급 수집이며 주문과 무관하다. 종목별 실패는 격리된다.
    """
    from app.core.config import get_settings
    from app.services.data_refresh_service import DataRefreshService
    from app.services.investor_flow_service import InvestorFlowService

    client = getattr(app.state, "investor_flow_client", None)
    if client is None:
        logger.warning("data refresh job skipped — investor_flow_client not initialized")
        return

    settings = get_settings()
    try:
        async with async_session_factory() as session:
            service = DataRefreshService(session, InvestorFlowService(session=session, client=client))
            symbols = await service.watchlist_symbols()
            summary = await service.refresh_investor_flows(
                symbols, lookback_days=settings.data_refresh_lookback_days
            )
        logger.info(
            "data refresh done: requested=%s succeeded=%s failed=%s rows=%s",
            summary.requested, summary.succeeded, summary.failed, summary.rows,
        )
        app.state.data_refresh_last_run_at = datetime.now(KST)
    except Exception as exc:  # noqa: BLE001 - 수집 실패가 스케줄러를 중단시키지 않도록
        logger.error("data refresh job failed: %s", exc_message(exc))
        app.state.data_refresh_last_error = exc_message(exc)


async def run_daily_report_job(app: FastAPI) -> None:
    """매일 장마감 후 일일 리서치 리포트를 생성한다 (C-2.29).

    주문/외부 API 호출 없이 DB 집계만 수행하므로 안전하다.
    """
    from app.domain.models.enums import MarketCode
    from app.services.daily_report_service import DailyReportService

    try:
        async with async_session_factory() as session:
            svc = DailyReportService(session)
            # 시장별로 따로 집계해 KR/US 리포트를 각각 생성한다.
            for market in (MarketCode.KR, MarketCode.US):
                report = await svc.generate(market=market)
                logger.info("daily report generated (%s): %s", market.value, report.summary)
        app.state.daily_report_last_run_at = datetime.now(KST)
    except Exception as exc:  # noqa: BLE001 - 리포트 실패가 스케줄러를 중단시키지 않도록
        logger.error("daily report job failed: %s", exc_message(exc))
        app.state.daily_report_last_error = exc_message(exc)


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
            overseas_client = getattr(app.state, "overseas_client", None)
            signal_service = SignalService(
                session,
                MarketDataService(broker, session, overseas_client=overseas_client),
                InvestorFlowRepository(session),
            )
            risk_service = RiskService(session, broker)
            overseas_broker = getattr(app.state, "overseas_broker_client", None)
            trade_service = TradeService(
                session, broker, risk_service, overseas_broker=overseas_broker
            )
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
        # - FAILED: job 자체가 crash하거나, 모든 version이 '실질적' 오류로 실패한 경우.
        #   레이트리밋/장외/네트워크 일시 오류만 있으면 FAILED로 보지 않는다(노이즈 억제).
        # - SKIPPED: 실행할 전략이 없음
        # - SUCCESS: 일부라도 성공 또는 일시적 오류만 (per-symbol 오류는 summary에 기록)
        non_transient = [e for e in errors if not is_transient_error(e["category"])]
        if errors and versions_succeeded == 0 and non_transient:
            status = SchedulerRunStatus.FAILED
            error_message = "; ".join(e["message"] for e in non_transient)
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
            overseas_broker = getattr(app.state, "overseas_broker_client", None)
            sync_service = OrderSyncService(session, broker, overseas_broker=overseas_broker)
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
        # - FAILED: KIS API 자체 조회 실패 (error_category 설정됨) — 단 레이트리밋/장외/네트워크
        #   일시 오류는 FAILED로 보지 않는다(노이즈 억제, summary에는 기록).
        # - SKIPPED: pending 주문 없음
        # - SUCCESS: API 성공 (per-trade 오류는 summary.errors에 기록)
        if result.error_category and not is_transient_error(result.error_category):
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


async def sync_trading_state_job(app: FastAPI) -> None:
    """전체 계좌에 대해 order sync + position reconciliation을 순서대로 실행한다.

    1단계: OrderSyncService로 pending/partial 주문 체결 동기화 (VTTC0081R/TTTC0081R)
    2단계: 각 계좌의 PositionReconciliationService로 잔고 정합성 검사
    - paper 계좌: mismatch 시 DB 자동 보정 + warning
    - real 계좌: mismatch 시 risk_event 기록 (자동 trading pause는 다음 phase)

    order sync 실패 시 reconciliation을 계속 진행하며 결과 summary에 warning을 남긴다.
    어느 한 계좌의 오류가 다른 계좌 처리나 scheduler 전체를 죽이지 않는다.
    """
    started_at = datetime.now(KST)
    status = SchedulerRunStatus.SUCCESS
    error_message: str | None = None
    summary: dict = {}

    try:
        async with async_session_factory() as session:
            broker = app.state.broker_client
            overseas_broker = getattr(app.state, "overseas_broker_client", None)
            svc = TradingStateSyncService(session, broker, overseas_broker=overseas_broker)
            results = await svc.sync_all_accounts()

        total_orders_checked = sum(r.orders_checked for r in results)
        total_orders_updated = sum(r.orders_updated for r in results)
        total_mismatches = sum(r.mismatches_count for r in results)
        total_risk_events = sum(r.risk_events_created for r in results)
        all_warnings = [w for r in results for w in r.warnings]
        all_order_errors = [e for r in results for e in r.order_sync_errors]
        all_position_errors = [e for r in results for e in r.position_errors]
        order_sync_error_categories = list({r.order_sync_error_category for r in results if r.order_sync_error_category})

        summary = {
            "accounts_synced": len(results),
            "orders_checked": total_orders_checked,
            "orders_updated": total_orders_updated,
            "mismatches_count": total_mismatches,
            "risk_events_created": total_risk_events,
            "order_sync_error_categories": order_sync_error_categories,
            "warnings": all_warnings,
            "errors": all_order_errors + all_position_errors,
            "per_account": [
                {
                    "account_id": r.account_id,
                    "broker_mode": r.broker_mode,
                    "orders_checked": r.orders_checked,
                    "orders_updated": r.orders_updated,
                    "mismatches_count": r.mismatches_count,
                    "risk_events_created": r.risk_events_created,
                    "positions_synced_to_db": r.positions_synced_to_db,
                    "warnings": r.warnings,
                }
                for r in results
            ],
        }

        if not results:
            status = SchedulerRunStatus.SKIPPED
        elif all_order_errors or all_position_errors:
            logger.warning(
                "trading state sync: completed with errors — order_errors=%d, position_errors=%d",
                len(all_order_errors), len(all_position_errors),
            )
        elif total_mismatches:
            logger.info(
                "trading state sync: %d mismatch(es) found across %d account(s)",
                total_mismatches, len(results),
            )

        app.state.trading_state_sync_last_error = None
        app.state.trading_state_sync_last_error_category = None
    except Exception as exc:  # noqa: BLE001 - 스케줄러는 예외로 죽으면 안 됨
        logger.exception("trading state sync job failed")
        status = SchedulerRunStatus.FAILED
        error_message = exc_message(exc)
        error_category = classify_exception(exc)
        summary = {"errors": [{"message": error_message, "category": error_category}]}
        app.state.trading_state_sync_last_error = error_message
        app.state.trading_state_sync_last_error_category = error_category
    finally:
        finished_at = datetime.now(KST)
        app.state.trading_state_sync_last_run_at = finished_at
        await _record_run(TRADING_STATE_SYNC_JOB_ID, started_at, finished_at, status, error_message, summary)
