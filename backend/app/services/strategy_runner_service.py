import logging
from dataclasses import dataclass
from datetime import datetime
from app.common.timezone import KST

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.market_session import is_closing_auction, is_signal_active
from app.core.config import get_settings
from app.domain.models.enums import MarketCode, TradeAttemptStatus
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import StrategyVersion
from app.domain.repositories.signal_log import SignalLogRepository
from app.domain.repositories.strategy import StrategyVersionRepository
from app.services.signal_service import SignalService
from app.services.trade_service import TradeService
from app.services.universe_resolver import ResolvedSymbol, UniverseResolver
from app.trading.broker.error_classifier import classify_exception, exc_message
from app.trading.strategy.base import Signal, Strategy
from app.trading.strategy.registry import create_strategy

logger = logging.getLogger(__name__)



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

    async def run_once(self, now: datetime | None = None) -> list[StrategyRunResult]:
        now = now or datetime.now(KST)
        versions = await self._strategy_version_repo.list_active()
        results: list[StrategyRunResult] = []
        # 이번 run 동안 종목별 캔들을 1회만 조회해 전략들이 공유한다(KIS 호출 절감).
        candle_cache: dict[str, list] = {}
        for version in versions:
            results.extend(await self._run_version(version, candle_cache, now))
        return results

    async def _resolve_symbols(
        self, version: StrategyVersion, params: dict
    ) -> list[ResolvedSymbol]:
        """전략 버전이 돌 종목 목록을 해석한다.

        universe가 설정돼 있으면 유니버스(스캐너 후보/관심종목)를 해석하고,
        아니면 단일 symbol_code를 리스트로 반환한다. 멀티마켓(KR/US)에서 종목마다
        시장/거래소가 다를 수 있어 ResolvedSymbol로 시세 라우팅 정보를 함께 전달한다.
        """
        universe = params.get("universe")
        if universe:
            resolver = UniverseResolver(self._session)
            # universe_market(KR/US)가 설정되면 해당 시장 종목만 해석한다(미설정=전체).
            universe_market = params.get("universe_market")
            market_filter = MarketCode(universe_market) if universe_market else None
            symbols = await resolver.resolve(
                universe, market=market_filter,
                lookback_days=int(params.get("universe_lookback_days", 5)),
            )
            if not symbols:
                logger.info(
                    "strategy_version_id=%s universe=%r market=%s 해석 결과 종목 없음 — 건너뜁니다.",
                    version.id, universe, universe_market,
                )
            return symbols
        symbol_code = params.get("symbol_code")
        if not symbol_code:
            return []
        # 단일 종목 모드: 전략 파라미터의 market/exchange를 그대로 사용.
        return [ResolvedSymbol(
            symbol_code=symbol_code,
            market=params.get("market", "KR"),
            exchange=params.get("exchange"),
        )]

    async def _run_version(
        self, version: StrategyVersion, candle_cache: dict | None = None,
        now: datetime | None = None,
    ) -> list[StrategyRunResult]:
        params = version.parameters or {}

        if not params.get("enabled", True):
            return []

        strategy_type = params.get("strategy_type", "")
        strategy = create_strategy(strategy_type, params)
        if strategy is None:
            return []

        symbols = await self._resolve_symbols(version, params)
        if not symbols:
            return []

        # 시장 세션 게이팅: 종목의 시장(KR/US)이 정규/종가동시호가 단계가 아니면 건너뛴다.
        # (장외 시간 KIS 호출/허위 신호 절감. 휴장일은 신선도 가드가 백스톱.)
        settings = get_settings()
        if settings.strategy_session_gating_enabled:
            ref = now or datetime.now(KST)
            include_extended = settings.signal_extended_sessions_enabled
            active = [
                r for r in symbols if is_signal_active(r.market, ref, include_extended)
            ]
            if not active:
                logger.debug(
                    "strategy_version_id=%s 모든 종목 시장 세션 비활성 — 건너뜁니다.", version.id
                )
                return []
            symbols = active

        # 안전: universe 모드는 신호 생성 전용 — 자동매매를 절대 켜지 않는다.
        universe_mode = bool(params.get("universe"))
        auto_trade_enabled = (
            False if universe_mode else bool(params.get("auto_trade_enabled", False))
        )

        ref = now or datetime.now(KST)
        exit_on_close = bool(params.get("exit_on_close", False))

        results: list[StrategyRunResult] = []
        for resolved in symbols:
            # Phase B: 종가 동시호가 단계 + exit_on_close 전략이면 '종가 청산' 매도로 강제.
            force_exit = exit_on_close and is_closing_auction(resolved.market, ref)
            results.append(
                await self._run_one(
                    version, strategy, resolved, params, auto_trade_enabled,
                    candle_cache, force_exit,
                )
            )
        return results

    async def _run_one(
        self,
        version: StrategyVersion,
        strategy: Strategy,
        resolved: ResolvedSymbol,
        params: dict,
        auto_trade_enabled: bool,
        candle_cache: dict | None = None,
        force_exit: bool = False,
    ) -> StrategyRunResult:
        symbol_code = resolved.symbol_code
        result = StrategyRunResult(
            strategy_version_id=version.id,
            symbol_code=symbol_code,
            signal_created=False,
            signal_id=None,
            auto_trade_enabled=auto_trade_enabled,
            trade_attempted=False,
        )

        try:
            log = await self._signal_service.generate_and_log_signal(
                strategy, symbol_code, version.id, strategy_params=params,
                candle_cache=candle_cache, market=resolved.market, exchange=resolved.exchange,
                force_exit=force_exit,
            )
        except Exception as exc:  # noqa: BLE001 - 한 종목 실패가 전체 runner를 중단시키지 않도록
            result.error = f"market data error: {exc_message(exc)}"
            result.error_category = classify_exception(exc)
            logger.error(
                "strategy_version_id=%s symbol=%s signal generation failed (%s): %s",
                version.id, symbol_code, result.error_category, exc_message(exc),
            )
            return result

        if log is None:
            return result

        result.signal_created = True
        result.signal_id = log.id

        if not auto_trade_enabled:
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
                account_id, signal, reason_source="strategy_runner",
                market=params.get("market", "KR"), exchange=params.get("exchange"),
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
