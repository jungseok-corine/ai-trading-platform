from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import TradeSide
from app.domain.models.signal_log import SignalLog
from app.domain.models.watchlist import WatchlistSymbol
from app.domain.repositories.signal_log import SignalLogRepository
from app.services.market_data_service import MarketDataService
from app.trading.strategy.base import Strategy
from app.trading.strategy.schemas import SignalLogRead

_METADATA_SKIP_KEYS = frozenset({"candle_ts", "short_ma", "long_ma"})


def _build_indicators(metadata: dict) -> dict | None:
    """Signal.metadata에서 indicators JSONB에 저장할 지표 dict를 만든다.

    candle_ts, short_ma, long_ma는 전용 컬럼에 이미 저장되므로 제외한다.
    Decimal/datetime 값은 JSON 직렬화를 위해 str로 변환한다.
    """
    indicators: dict = {}
    for k, v in metadata.items():
        if k in _METADATA_SKIP_KEYS:
            continue
        if v is None:
            continue
        if isinstance(v, Decimal):
            indicators[k] = str(v)
        elif isinstance(v, datetime):
            indicators[k] = v.isoformat()
        else:
            indicators[k] = v
    return indicators or None

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
            # 시그널 없어도 get_recent_candles에서 flush된 market_data를 커밋한다.
            await self._session.commit()
            return None

        metadata = signal.metadata or {}
        candle_ts = metadata.get("candle_ts")

        if await self._signal_log_repo.exists_for_candle(
            signal.strategy_version_id, signal.symbol_code, signal.side, candle_ts
        ):
            await self._session.commit()
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
            signal_price=signal.price,
            quantity=signal.quantity,
            indicators=_build_indicators(metadata),
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

    async def list_signals(
        self,
        limit: int = 50,
        offset: int = 0,
        signal_type: TradeSide | None = None,
        symbol_code: str | None = None,
        strategy_version_id: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[SignalLogRead]:
        logs = await self._signal_log_repo.list_filtered(
            limit=limit,
            offset=offset,
            signal_type=signal_type,
            symbol_code=symbol_code,
            strategy_version_id=strategy_version_id,
            date_from=date_from,
            date_to=date_to,
        )
        name_map = await self._fetch_symbol_name_map({log.symbol_code for log in logs})
        return [self._to_read(log, name_map) for log in logs]

    async def get_signal(self, signal_id: int) -> SignalLogRead | None:
        log = await self._signal_log_repo.get(signal_id)
        if log is None:
            return None
        name_map = await self._fetch_symbol_name_map({log.symbol_code})
        return self._to_read(log, name_map)
