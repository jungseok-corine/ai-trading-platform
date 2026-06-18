import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import TradeAttemptStatus
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import StrategyVersion
from app.domain.repositories.signal_log import SignalLogRepository
from app.domain.repositories.strategy import StrategyVersionRepository
from app.services.signal_service import SignalService
from app.services.trade_service import TradeService
from app.trading.broker.error_classifier import classify_exception, exc_message
from app.trading.strategy.base import Signal
from app.trading.strategy.moving_average_cross import MovingAverageCrossStrategy

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

STRATEGY_TYPE_MOVING_AVERAGE_CROSS = "moving_average_cross"


@dataclass
class StrategyRunResult:
    """전략 1개에 대한 1회 실행 결과 (Signal 생성 + 자동 주문 시도 결과)."""

    strategy_version_id: int | None
    symbol_code: str
    signal_created: bool
    signal_id: int | None
    auto_trade_enabled: bool
    trade_attempted: bool
    trade_approved: bool | None = None
    trade_id: int | None = None
    rejection_reason: str | None = None
    error: str | None = None
    error_category: str | None = None


class StrategyRunnerService:
    """status가 active/testing인 strategy_versions를 조회해 전략을 실행하고
    Signal이 생성되면 signal_logs에 저장한다.

    parameters.auto_trade_enabled가 true인 전략에 한해서만, 생성된 Signal을
    TradeService.execute_signal()에 전달해 RiskManager 검증 → (승인 시) KIS 주문 → trades
    저장까지 진행한다. auto_trade_enabled가 없거나 false이면 signal_logs 저장까지만 한다.
    """

    def __init__(
        self,
        session: AsyncSession,
        signal_service: SignalService,
        trade_service: TradeService | None = None,
    ) -> None:
        self._session = session
        self._signal_service = signal_service
        self._trade_service = trade_service
        self._strategy_version_repo = StrategyVersionRepository(session)
        self._signal_log_repo = SignalLogRepository(session)

    async def run_once(self) -> list[StrategyRunResult]:
        versions = await self._strategy_version_repo.list_active()
        results: list[StrategyRunResult] = []
        for version in versions:
            result = await self._run_version(version)
            if result is not None:
                results.append(result)
        return results

    async def _run_version(self, version: StrategyVersion) -> StrategyRunResult | None:
        params = version.parameters or {}

        if not params.get("enabled", True):
            return None
        if params.get("strategy_type") != STRATEGY_TYPE_MOVING_AVERAGE_CROSS:
            return None

        symbol_code = params.get("symbol_code")
        if not symbol_code:
            return None

        result = StrategyRunResult(
            strategy_version_id=version.id,
            symbol_code=symbol_code,
            signal_created=False,
            signal_id=None,
            auto_trade_enabled=bool(params.get("auto_trade_enabled", False)),
            trade_attempted=False,
        )

        strategy = MovingAverageCrossStrategy(
            short_window=params.get("short_window", 5),
            long_window=params.get("long_window", 20),
            quantity=params.get("quantity", 1),
        )

        try:
            log = await self._signal_service.generate_and_log_signal(strategy, symbol_code, version.id)
        except Exception as exc:  # noqa: BLE001 - 한 종목 실패가 전체 runner를 중단시키지 않도록
            result.error = f"market data error: {exc_message(exc)}"
            result.error_category = classify_exception(exc)
            logger.error(
                "strategy_version_id=%s signal generation failed (%s): %s",
                version.id, result.error_category, exc_message(exc),
            )
            return result

        if log is None:
            return result

        result.signal_created = True
        result.signal_id = log.id

        if not result.auto_trade_enabled:
            return result

        await self._attempt_auto_trade(version, params, log, result)
        return result

    async def _attempt_auto_trade(
        self, version: StrategyVersion, params: dict, log: SignalLog, result: StrategyRunResult
    ) -> None:
        if log.trade_attempt_status != TradeAttemptStatus.NOT_ATTEMPTED:
            result.error = (
                f"이미 주문이 시도된 신호입니다 (signal_id={log.id}, "
                f"status={log.trade_attempt_status.value}). 중복 주문을 방지합니다."
            )
            logger.info(
                "strategy_version_id=%s signal_id=%s: 주문 시도 중복 방지 (status=%s)",
                version.id, log.id, log.trade_attempt_status.value,
            )
            return

        account_id = params.get("account_id")
        if account_id is None:
            result.error = "auto_trade_enabled=true 이지만 parameters.account_id가 설정되지 않았습니다."
            logger.warning("strategy_version_id=%s: %s", version.id, result.error)
            return

        from app.services.trading_guard_service import TradingGuardService  # noqa: PLC0415

        if await TradingGuardService(self._session).is_paused(account_id):
            result.error = f"자동매매가 일시 중지되어 있습니다 (account_id={account_id}). API로 수동 재개 필요."
            result.trade_attempted = False
            logger.info(
                "strategy_version_id=%s: auto-trade skipped — trading guard is paused for account=%s",
                version.id, account_id,
            )
            return

        if self._trade_service is None:
            result.error = "TradeService가 설정되지 않아 자동 주문을 실행할 수 없습니다."
            logger.warning("strategy_version_id=%s: %s", version.id, result.error)
            return

        signal = Signal(
            symbol_code=log.symbol_code,
            side=log.signal_type,
            quantity=log.quantity or params.get("quantity", 1),
            price=log.price,
            reason=log.reason or "",
            strategy_version_id=log.strategy_version_id,
        )

        result.trade_attempted = True
        logger.info(
            "auto-trade attempt: strategy_version_id=%s account_id=%s symbol=%s side=%s qty=%s price=%s",
            version.id, account_id, signal.symbol_code, signal.side, signal.quantity, signal.price,
        )

        try:
            placement = await self._trade_service.execute_signal(
                account_id, signal, reason_source="strategy_runner"
            )
        except Exception as exc:  # noqa: BLE001 - 주문 오류가 전체 runner를 중단시키지 않도록
            result.error = f"order error: {exc_message(exc)}"
            result.error_category = classify_exception(exc)
            logger.error(
                "strategy_version_id=%s auto-trade order failed (%s): %s",
                version.id, result.error_category, exc_message(exc),
            )
            await self._mark_trade_attempt(log, TradeAttemptStatus.ERROR)
            return

        result.trade_approved = placement.approved
        if placement.approved and placement.trade is not None:
            result.trade_id = placement.trade.id
            logger.info(
                "auto-trade approved: strategy_version_id=%s trade_id=%s", version.id, placement.trade.id
            )
            await self._mark_trade_attempt(log, TradeAttemptStatus.APPROVED, trade_id=placement.trade.id)
        else:
            result.rejection_reason = placement.reason
            logger.info(
                "auto-trade rejected: strategy_version_id=%s rule=%s reason=%s",
                version.id, placement.rule_name, placement.reason,
            )
            await self._mark_trade_attempt(log, TradeAttemptStatus.REJECTED)

    async def _mark_trade_attempt(
        self, log: SignalLog, status: TradeAttemptStatus, trade_id: int | None = None
    ) -> None:
        await self._signal_log_repo.update(
            log,
            trade_attempt_status=status,
            trade_attempted_at=datetime.now(KST),
            trade_id=trade_id,
        )
        await self._session.commit()
