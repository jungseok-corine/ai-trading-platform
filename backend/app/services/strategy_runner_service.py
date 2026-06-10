from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import StrategyVersion
from app.domain.repositories.strategy import StrategyVersionRepository
from app.services.signal_service import SignalService
from app.trading.strategy.moving_average_cross import MovingAverageCrossStrategy

STRATEGY_TYPE_MOVING_AVERAGE_CROSS = "moving_average_cross"


class StrategyRunnerService:
    """status가 active/testing인 strategy_versions를 조회해 전략을 실행하고
    Signal이 생성되면 signal_logs에 저장한다. 주문은 실행하지 않는다.
    """

    def __init__(self, session: AsyncSession, signal_service: SignalService) -> None:
        self._session = session
        self._signal_service = signal_service
        self._strategy_version_repo = StrategyVersionRepository(session)

    async def run_once(self) -> list[SignalLog]:
        versions = await self._strategy_version_repo.list_active()
        results: list[SignalLog] = []
        for version in versions:
            log = await self._run_version(version)
            if log is not None:
                results.append(log)
        return results

    async def _run_version(self, version: StrategyVersion) -> SignalLog | None:
        params = version.parameters or {}

        if not params.get("enabled", True):
            return None
        if params.get("strategy_type") != STRATEGY_TYPE_MOVING_AVERAGE_CROSS:
            return None

        symbol_code = params.get("symbol_code")
        if not symbol_code:
            return None

        strategy = MovingAverageCrossStrategy(
            short_window=params.get("short_window", 5),
            long_window=params.get("long_window", 20),
            quantity=params.get("quantity", 1),
        )
        return await self._signal_service.generate_and_log_signal(strategy, symbol_code, version.id)
