from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.signal_log import SignalLog
from app.domain.models.watchlist import WatchlistSymbol
from app.domain.repositories.signal_log import SignalLogRepository
from app.services.market_data_service import MarketDataService
from app.trading.strategy.base import Strategy
from app.trading.strategy.schemas import SignalLogRead

KST = ZoneInfo("Asia/Seoul")


class SignalService:
    """Strategy를 실행해 Signal을 생성하고 signal_logs에 기록한다.

    아직 주문을 실행하지 않는다 (시장 데이터 → 전략 → Signal 생성 → DB 저장까지).
    """

    def __init__(self, session: AsyncSession, market_data_service: MarketDataService) -> None:
        self._session = session
        self._market_data_service = market_data_service
        self._signal_log_repo = SignalLogRepository(session)

    async def generate_and_log_signal(
        self,
        strategy: Strategy,
        symbol_code: str,
        strategy_version_id: int | None = None,
    ) -> SignalLog | None:
        candles = await self._market_data_service.get_recent_candles(symbol_code)
        signal = strategy.generate_signal(symbol_code, candles, strategy_version_id)
        if signal is None:
            return None

        metadata = signal.metadata or {}
        candle_ts = metadata.get("candle_ts")

        if await self._signal_log_repo.exists_for_candle(
            signal.strategy_version_id, signal.symbol_code, signal.side, candle_ts
        ):
            return None

        log = await self._signal_log_repo.create(
            symbol_code=signal.symbol_code,
            strategy_version_id=signal.strategy_version_id,
            signal_type=signal.side,
            generated_at=datetime.now(KST),
            candle_ts=candle_ts,
            reason=signal.reason,
            short_ma=metadata.get("short_ma"),
            long_ma=metadata.get("long_ma"),
            price=signal.price,
            quantity=signal.quantity,
        )
        await self._session.commit()
        return log

    async def _fetch_symbol_name_map(self, symbol_codes: set[str]) -> dict[str, str]:
        """watchlist_symbols에서 symbol_code → symbol_name 매핑을 가져온다.

        동일 symbol_code가 여러 watchlist에 등록된 경우 첫 번째 non-null 이름을 사용한다.
        """
        if not symbol_codes:
            return {}
        result = await self._session.execute(
            select(WatchlistSymbol.symbol_code, WatchlistSymbol.symbol_name)
            .where(WatchlistSymbol.symbol_code.in_(symbol_codes))
            .where(WatchlistSymbol.symbol_name.is_not(None))
        )
        name_map: dict[str, str] = {}
        for code, name in result.all():
            if code not in name_map:
                name_map[code] = name
        return name_map

    def _to_read(self, log: SignalLog, name_map: dict[str, str]) -> SignalLogRead:
        symbol_name = name_map.get(log.symbol_code)
        symbol_display = f"{symbol_name} ({log.symbol_code})" if symbol_name else None
        return SignalLogRead.model_validate(log).model_copy(
            update={"symbol_name": symbol_name, "symbol_display": symbol_display}
        )

    async def list_signals(self, limit: int = 100, offset: int = 0) -> list[SignalLogRead]:
        logs = await self._signal_log_repo.list(limit, offset)
        name_map = await self._fetch_symbol_name_map({log.symbol_code for log in logs})
        return [self._to_read(log, name_map) for log in logs]

    async def get_signal(self, signal_id: int) -> SignalLogRead | None:
        log = await self._signal_log_repo.get(signal_id)
        if log is None:
            return None
        name_map = await self._fetch_symbol_name_map({log.symbol_code})
        return self._to_read(log, name_map)
