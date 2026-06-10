from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker_client
from app.db.session import get_db
from app.domain.repositories.strategy import StrategyVersionRepository
from app.services.market_data_service import MarketDataService
from app.services.signal_service import SignalService
from app.services.strategy_runner_service import StrategyRunnerService
from app.trading.broker.base import BrokerClient
from app.trading.broker.exceptions import KISAPIError
from app.trading.strategy.schemas import EngineStatusResponse, SignalLogRead

router = APIRouter(prefix="/engine", tags=["engine"])

KST = ZoneInfo("Asia/Seoul")


@router.get("/status", response_model=EngineStatusResponse)
async def get_engine_status(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> EngineStatusResponse:
    scheduler = getattr(request.app.state, "scheduler", None)
    registered_jobs = [job.id for job in scheduler.get_jobs()] if scheduler is not None else []
    active_versions = await StrategyVersionRepository(session).list_active()

    return EngineStatusResponse(
        scheduler_running=scheduler is not None and scheduler.running,
        registered_jobs=registered_jobs,
        last_run_at=getattr(request.app.state, "scheduler_last_run_at", None),
        last_error=getattr(request.app.state, "scheduler_last_error", None),
        active_strategy_count=len(active_versions),
    )


@router.post("/run-once", response_model=list[SignalLogRead])
async def run_once(
    request: Request,
    session: AsyncSession = Depends(get_db),
    broker: BrokerClient = Depends(get_broker_client),
) -> list[SignalLogRead]:
    """활성 전략을 즉시 1회 실행한다 (테스트/수동 실행용). 자동 주문은 실행하지 않는다."""
    runner = StrategyRunnerService(session, SignalService(session, MarketDataService(broker)))

    try:
        results = await runner.run_once()
    except KISAPIError as e:
        request.app.state.scheduler_last_error = e.msg1
        request.app.state.scheduler_last_run_at = datetime.now(KST)
        raise HTTPException(status_code=502, detail=e.msg1) from e

    request.app.state.scheduler_last_error = None
    request.app.state.scheduler_last_run_at = datetime.now(KST)
    return [SignalLogRead.model_validate(log) for log in results]
