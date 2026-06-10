import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from app.db.session import async_session_factory
from app.services.market_data_service import MarketDataService
from app.services.signal_service import SignalService
from app.services.strategy_runner_service import StrategyRunnerService

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


async def run_strategy_job(app: FastAPI) -> None:
    """활성 전략을 1회 실행하고 Signal이 생성되면 signal_logs에 저장한다.

    자동 주문은 실행하지 않는다. 실행 결과(시각/에러)는 app.state에 기록되어
    /api/v1/engine/status 에서 조회할 수 있다.
    """
    try:
        async with async_session_factory() as session:
            broker = app.state.broker_client
            signal_service = SignalService(session, MarketDataService(broker))
            runner = StrategyRunnerService(session, signal_service)
            results = await runner.run_once()

        if results:
            logger.info("strategy scheduler: %d signal(s) generated", len(results))

        app.state.scheduler_last_error = None
    except Exception as exc:  # noqa: BLE001 - 스케줄러는 예외로 죽으면 안 됨
        logger.exception("strategy scheduler job failed")
        app.state.scheduler_last_error = str(exc)
    finally:
        app.state.scheduler_last_run_at = datetime.now(KST)
