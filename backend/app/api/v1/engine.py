from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker_client
from app.db.session import get_db
from app.domain.repositories.strategy import StrategyVersionRepository
from app.services.market_data_service import MarketDataService
from app.services.order_sync_service import OrderSyncService
from app.services.risk_service import RiskService
from app.services.scheduler_run_service import SchedulerRunService
from app.services.signal_service import SignalService
from app.services.strategy_runner_service import StrategyRunnerService
from app.services.trade_service import TradeService
from app.trading.broker.base import BrokerClient
from app.trading.strategy.schemas import (
    EngineStatusResponse,
    OrderSyncResultRead,
    SchedulerRunRead,
    StrategyRunResultRead,
)

router = APIRouter(prefix="/engine", tags=["engine"])

KST = ZoneInfo("Asia/Seoul")


def get_strategy_runner_service(
    session: AsyncSession = Depends(get_db),
    broker: BrokerClient = Depends(get_broker_client),
) -> StrategyRunnerService:
    signal_service = SignalService(session, MarketDataService(broker))
    risk_service = RiskService(session, broker)
    trade_service = TradeService(session, broker, risk_service)
    return StrategyRunnerService(session, signal_service, trade_service)


def get_order_sync_service(
    session: AsyncSession = Depends(get_db),
    broker: BrokerClient = Depends(get_broker_client),
) -> OrderSyncService:
    return OrderSyncService(session, broker)


@router.get("/status", response_model=EngineStatusResponse)
async def get_engine_status(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> EngineStatusResponse:
    scheduler = getattr(request.app.state, "scheduler", None)
    registered_jobs = [job.id for job in scheduler.get_jobs()] if scheduler is not None else []
    active_versions = await StrategyVersionRepository(session).list_active()
    auto_trade_enabled_count = sum(
        1 for v in active_versions if (v.parameters or {}).get("auto_trade_enabled", False)
    )
    recent_run_has_failure = await SchedulerRunService(session).has_recent_failure(limit=20)

    return EngineStatusResponse(
        scheduler_running=scheduler is not None and scheduler.running,
        registered_jobs=registered_jobs,
        last_run_at=getattr(request.app.state, "scheduler_last_run_at", None),
        last_error=getattr(request.app.state, "scheduler_last_error", None),
        active_strategy_count=len(active_versions),
        order_sync_last_run_at=getattr(request.app.state, "order_sync_last_run_at", None),
        order_sync_last_error=getattr(request.app.state, "order_sync_last_error", None),
        recent_run_has_failure=recent_run_has_failure,
        auto_trade_enabled_count=auto_trade_enabled_count,
    )


@router.post("/run-once", response_model=list[StrategyRunResultRead])
async def run_once(
    request: Request,
    runner: StrategyRunnerService = Depends(get_strategy_runner_service),
) -> list[StrategyRunResultRead]:
    """활성 전략을 즉시 1회 실행한다 (테스트/수동 실행용).

    auto_trade_enabled=true인 전략에 한해 RiskManager 검증 → (승인 시) KIS 주문까지 시도한다.
    KIS/주문 관련 오류는 전략별 결과의 error 필드에 기록되며 전체 요청을 실패시키지 않는다.
    """
    try:
        results = await runner.run_once()
        request.app.state.scheduler_last_error = None
    except Exception as e:
        request.app.state.scheduler_last_error = str(e)
        request.app.state.scheduler_last_run_at = datetime.now(KST)
        raise

    request.app.state.scheduler_last_run_at = datetime.now(KST)
    return [StrategyRunResultRead.model_validate(r) for r in results]


@router.get("/runs", response_model=list[SchedulerRunRead])
async def list_scheduler_runs(
    limit: int = 20,
    session: AsyncSession = Depends(get_db),
) -> list[SchedulerRunRead]:
    """최근 scheduler job(strategy_runner, order_sync) 실행 기록을 조회한다."""
    runs = await SchedulerRunService(session).list_recent(limit)
    return [SchedulerRunRead.model_validate(r) for r in runs]


@router.post("/sync-orders", response_model=OrderSyncResultRead)
async def sync_orders(
    request: Request,
    sync_service: OrderSyncService = Depends(get_order_sync_service),
) -> OrderSyncResultRead:
    """pending/partial 주문의 체결 상태를 즉시 1회 동기화한다 (테스트/수동 실행용)."""
    result = await sync_service.sync_pending_orders()
    request.app.state.order_sync_last_error = "; ".join(result.errors) if result.errors else None
    request.app.state.order_sync_last_run_at = datetime.now(KST)
    return OrderSyncResultRead(
        checked=result.checked,
        updated=result.updated,
        matched=result.matched,
        unmatched=result.unmatched,
        unmatched_order_ids=result.unmatched_order_ids,
        errors=result.errors,
        error_category=result.error_category,
        skipped_reason=result.skipped_reason,
    )
