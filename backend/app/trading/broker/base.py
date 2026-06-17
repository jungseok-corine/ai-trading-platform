from abc import ABC, abstractmethod

from app.trading.broker.schemas import (
    AccountBalance,
    AccountHolding,
    BrokerPositionItem,
    MinuteCandle,
    OrderExecution,
    OrderRequest,
    OrderResult,
    PriceQuote,
)


class BrokerClient(ABC):
    """Paper/Live 공통 브로커 인터페이스.

    구현체(KISPaperBrokerClient, 향후 KISRealBrokerClient)는 이 인터페이스를
    통해 TradingEngine/Service 계층에 노출되며, 실제 KIS API 호출 코드는
    구현체 내부에만 위치한다.
    """

    @abstractmethod
    async def get_current_price(self, symbol_code: str) -> PriceQuote: ...

    @abstractmethod
    async def get_minute_candles(
        self,
        symbol_code: str,
        target_time: str | None = None,
        include_past_data: bool = True,
    ) -> list[MinuteCandle]: ...

    @abstractmethod
    async def get_account_balance(self) -> AccountBalance: ...

    @abstractmethod
    async def get_account_positions(self) -> list[AccountHolding]: ...

    @abstractmethod
    async def place_order(self, order: OrderRequest) -> OrderResult: ...

    @abstractmethod
    async def get_daily_executions(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> list[OrderExecution]: ...

    async def get_broker_positions(self) -> list[BrokerPositionItem]:
        """브로커 잔고 포지션 목록을 BrokerPositionItem으로 반환한다.

        기본 구현은 NotImplementedError를 발생시킨다. 포지션 정합성 검사(C-2.10)를
        지원하는 구현체는 이 메서드를 오버라이드해야 한다.
        """
        raise NotImplementedError(f"{type(self).__name__} does not implement get_broker_positions")
