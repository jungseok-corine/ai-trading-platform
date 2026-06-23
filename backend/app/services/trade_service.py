import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.trade import Trade
from app.domain.repositories.trade import TradeRepository
from app.services.risk_service import RiskService
from app.trading.broker.base import BrokerClient
from app.trading.broker.schemas import OrderRequest, OrderType
from app.trading.order.schemas import OrderCreateRequest
from app.trading.pricing.tick import round_price_to_tick, round_us_price_to_cent
from app.trading.strategy.base import Signal

logger = logging.getLogger(__name__)


@dataclass
class OrderPlacementResult:
    approved: bool
    trade: Trade | None
    rule_name: str | None = None
    reason: str | None = None


class TradeService:
    """Signal을 RiskManager 검증 후 BrokerClient를 통해 실행하고 trades에 기록한다.

    수동 주문(API)과 자동 주문(StrategyRunnerService)이 모두 execute_signal()을
    통해 동일한 RiskManager/주문 실행 경로를 거친다.
    """

    def __init__(
        self,
        session: AsyncSession,
        broker: BrokerClient,
        risk_service: RiskService,
        overseas_broker: BrokerClient | None = None,
    ) -> None:
        self._session = session
        self._broker = broker
        self._overseas_broker = overseas_broker
        self._risk_service = risk_service
        self._trade_repo = TradeRepository(session)

    async def get_available_cash(self, market: str = "KR"):
        """해당 시장 계좌의 가용 현금(총예수금)을 반환한다(포지션 사이징용)."""
        broker = self._select_broker(market)
        balance = await broker.get_account_balance()
        return balance.summary.total_deposit

    def _select_broker(self, market: str) -> BrokerClient:
        """주문 시장(KR/US)에 맞는 브로커를 고른다.

        US는 해외 브로커가 구성된 경우에만 사용한다(없으면 명확히 실패).
        """
        if market == "US":
            if self._overseas_broker is None:
                raise RuntimeError(
                    "미국 시장 주문을 위한 해외 브로커(overseas_broker)가 구성되지 않았습니다."
                )
            return self._overseas_broker
        return self._broker

    async def place_order(self, request: OrderCreateRequest) -> OrderPlacementResult:
        signal = Signal(
            symbol_code=request.symbol_code,
            side=request.side,
            quantity=request.quantity,
            price=request.price,
            reason=request.reason or "",
            strategy_version_id=request.strategy_version_id,
        )
        return await self.execute_signal(
            request.account_id, signal, order_type=request.order_type, reason_source="manual",
            market=request.market, exchange=request.exchange,
        )

    async def execute_signal(
        self,
        account_id: int,
        signal: Signal,
        order_type: OrderType = OrderType.LIMIT,
        reason_source: str = "manual",
        market: str = "KR",
        exchange: str | None = None,
    ) -> OrderPlacementResult:
        """Signal을 RiskManager로 검증 후 승인되면 주문을 실행하고 trades에 기록한다.

        거부되면 trades는 저장하지 않는다 (risk_events는 RiskService가 기록).
        """
        logger.info(
            "execute_signal start: source=%s account_id=%s market=%s symbol=%s side=%s qty=%s price=%s",
            reason_source, account_id, market, signal.symbol_code, signal.side,
            signal.quantity, signal.price,
        )

        broker = self._select_broker(market)
        # 리스크 검증에서 통화 환산(USD→KRW)을 적용하도록 신호에 시장을 표시한다.
        signal.market = market

        # C-2.13: Real trading disabled guard — defense-in-depth, checked before any DB/broker call.
        # KISRealBrokerClient exposes real_trading_enabled; paper brokers do not have this attr.
        if not getattr(broker, "real_trading_enabled", True):
            logger.warning(
                "execute_signal blocked: real_trading_enabled=False for account=%s", account_id
            )
            return OrderPlacementResult(
                approved=False,
                trade=None,
                rule_name="real_trading_disabled",
                reason=(
                    "실전 주문이 비활성화되어 있습니다 (real_trading_enabled=False). "
                    "KIS_REAL_TRADING_ENABLED=true를 설정해야 실전 주문이 가능합니다."
                ),
            )

        from app.services.trading_guard_service import TradingGuardService  # noqa: PLC0415

        if await TradingGuardService(self._session).is_paused(account_id):
            logger.warning(
                "execute_signal blocked: trading is paused for account=%s", account_id
            )
            return OrderPlacementResult(
                approved=False,
                trade=None,
                rule_name="trading_paused",
                reason="Auto-trading is paused for this account. Resume via POST /api/v1/trading-guard/resume.",
            )

        risk_result = await self._risk_service.validate_signal(account_id, signal)
        if not risk_result.approved:
            logger.info(
                "execute_signal rejected: source=%s account_id=%s rule=%s reason=%s",
                reason_source, account_id, risk_result.rule_name, risk_result.reason,
            )
            return OrderPlacementResult(
                approved=False,
                trade=None,
                rule_name=risk_result.rule_name,
                reason=risk_result.reason,
            )

        adjusted_price = signal.price
        market_condition: dict | None = None
        if order_type == OrderType.LIMIT:
            # 시장별 호가단위: 미국은 1센트($0.01), 국내는 KRX 정수 호가단위.
            if market == "US":
                adjusted_price = round_us_price_to_cent(signal.price, signal.side)
            else:
                adjusted_price = round_price_to_tick(signal.price, signal.side)
            if adjusted_price != signal.price:
                logger.info(
                    "price tick adjustment: source=%s symbol=%s side=%s original_price=%s adjusted_price=%s",
                    reason_source, signal.symbol_code, signal.side, signal.price, adjusted_price,
                )
            market_condition = {
                "price_tick_adjustment": {
                    "original_price": str(signal.price),
                    "adjusted_price": str(adjusted_price),
                }
            }

        order_result = await broker.place_order(
            OrderRequest(
                symbol_code=signal.symbol_code,
                side=signal.side,
                quantity=signal.quantity,
                price=adjusted_price,
                order_type=order_type,
                exchange=exchange,
            )
        )

        trade = await self._trade_repo.create(
            account_id=account_id,
            strategy_version_id=signal.strategy_version_id,
            symbol_code=signal.symbol_code,
            market=market,
            side=signal.side,
            entry_time=order_result.ordered_at,
            entry_price=adjusted_price,
            quantity=signal.quantity,
            entry_reason=signal.reason,
            market_condition=market_condition,
            order_status=order_result.order_status,
            broker_order_id=order_result.broker_order_id,
            org_no=order_result.org_no,
        )
        await self._session.commit()
        logger.info(
            "execute_signal approved: source=%s account_id=%s trade_id=%s broker_order_id=%s",
            reason_source, account_id, trade.id, order_result.broker_order_id,
        )
        return OrderPlacementResult(approved=True, trade=trade)

    async def list_trades(self, account_id: int | None, limit: int, offset: int) -> list[Trade]:
        if account_id is not None:
            return await self._trade_repo.list_by_account(account_id, limit, offset)
        return await self._trade_repo.list(limit, offset)

    async def get_trade(self, trade_id: int) -> Trade | None:
        return await self._trade_repo.get(trade_id)
