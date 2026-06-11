from abc import ABC, abstractmethod

from app.trading.broker.schemas import (
    AccountBalance,
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
    async def place_order(self, order: OrderRequest) -> OrderResult: ...

    @abstractmethod
    async def get_daily_executions(self, target_date: str | None = None) -> list[OrderExecution]: ...
