from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from app.common.timezone import KST

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models.enums import TradeSide
from app.domain.models.signal_log import SignalLog
from app.domain.models.watchlist import WatchlistSymbol
from app.domain.repositories.investor_flow import InvestorFlowRepository
from app.domain.repositories.signal_log import SignalLogRepository
from app.services.market_data_service import MarketDataService, _timeframe_to_nmin
from app.trading.broker.schemas import MinuteCandle
from app.trading.strategy.base import Strategy
from app.trading.strategy.context import StrategyContext
from app.trading.strategy.indicators import candle_timestamp
from app.trading.strategy.schemas import SignalLogRead

logger = logging.getLogger(__name__)

_METADATA_SKIP_KEYS = frozenset({"candle_ts", "short_ma", "long_ma"})


def _latest_candle_age_minutes(candles: list[MinuteCandle], now: datetime) -> float | None:
    """가장 최신 캔들이 now 기준 몇 분 전 데이터인지 반환한다.

    캔들의 business_date/trade_time을 파싱할 수 없으면 None(판단 불가).
    """
    if not candles:
        return None
    try:
        latest_ts = candle_timestamp(candles[-1])
    except (ValueError, TypeError):
        return None
    return (now - latest_ts).total_seconds() / 60.0


def _is_candle_stale(
    candles: list[MinuteCandle], timeframe: str, now: datetime, max_staleness_minutes: int
) -> bool:
    """최신 캔들이 신선도 임계치를 초과해 오래되었는지(스테일) 판단한다.

    장 마감/휴장으로 시세가 멈추면 KIS는 마지막(또는 종가로 평탄한) 캔들을 계속
    돌려준다. 이때 임계치를 넘는 오래된 캔들이면 신호를 만들지 않는다.
    임계치는 설정값과 캔들 간격(timeframe)의 3배 중 큰 값을 사용한다(저유동 종목의
    정상적인 캔들 공백으로 인한 허위 차단을 줄이기 위함).
    max_staleness_minutes <= 0 이면 가드를 비활성화한다.
    """
    if max_staleness_minutes <= 0:
        return False
    age = _latest_candle_age_minutes(candles, now)
    if age is None:
        return False  # 판단 불가 시 차단하지 않음(다른 가드가 보완)
    threshold = max(float(max_staleness_minutes), _timeframe_to_nmin(timeframe) * 3.0)
    return age > threshold


def _build_indicators(metadata: dict) -> dict | None:
    """Signal.metadata에서 indicators JSONB에 저장할 지표 dict를 만든다.

    candle_ts, short_ma, long_ma는 전용 컬럼에 이미 저장되므로 제외한다.
    Decimal/datetime/date 값은 JSON 직렬화를 위해 str로 변환한다.
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
        elif isinstance(v, date):
            indicators[k] = v.isoformat()
        else:
            indicators[k] = v
    return indicators or None




def _candle_date(candles: list[MinuteCandle]) -> date | None:
    """최신 캔들의 business_date("YYYYMMDD")를 date 객체로 변환한다."""
    if not candles:
        return None
    bd = candles[-1].business_date
    if len(bd) != 8:
        return None
    return date(int(bd[:4]), int(bd[4:6]), int(bd[6:8]))


class SignalService:
    """Strategy를 실행해 Signal을 생성하고 signal_logs에 기록한다.

    아직 주문을 실행하지 않는다 (시장 데이터 → 전략 → Signal 생성 → DB 저장까지).
    investor_flow_repo가 주입된 경우, strategy_params를 참고해 StrategyContext를 조립해
    generate_signal에 전달한다. 전략 클래스 안에서는 DB/네트워크 접근을 하지 않는다.
    """

    def __init__(
        self,
        session: AsyncSession,
        market_data_service: MarketDataService,
        investor_flow_repo: InvestorFlowRepository | None = None,
    ) -> None:
        self._session = session
        self._market_data_service = market_data_service
        self._investor_flow_repo = investor_flow_repo
        self._signal_log_repo = SignalLogRepository(session)

    async def _build_strategy_context(
        self,
        symbol_code: str,
        candles: list[MinuteCandle],
        strategy_params: dict,
    ) -> StrategyContext:
        """investor_flows DB에서 look-ahead 방지된 데이터를 조회해 StrategyContext를 조립한다.

        look-ahead 방지: 캔들 당일(business_date)의 수급은 장마감 후 확정되므로
        trade_date < candle_date 인 데이터만 사용한다.
        """
        flow_lookback_days = int(strategy_params.get("flow_lookback_days", 5))
        max_flow_age_days = int(strategy_params.get("max_flow_age_days", 5))

        candle_date = _candle_date(candles) or date.today()
        # look-ahead 방지: 캔들 당일 제외, 그 이전 데이터만 사용
        date_to = candle_date - timedelta(days=1)
        date_from = date_to - timedelta(days=flow_lookback_days - 1)

        assert self._investor_flow_repo is not None
        flows = await self._investor_flow_repo.list_by_symbol(
            symbol_code, date_from=date_from, date_to=date_to
        )

        latest_flow = flows[0] if flows else None  # list_by_symbol은 최신순 정렬

        flow_data_available = latest_flow is not None
        flow_data_date = latest_flow.trade_date if latest_flow else None
        flow_data_staleness_days: int | None = None

        if flow_data_date is not None:
            flow_data_staleness_days = (candle_date - flow_data_date).days
            # staleness가 max_flow_age_days 초과이면 flow_data_available=False 표시
            if flow_data_staleness_days > max_flow_age_days:
                flow_data_available = False

        return StrategyContext(
            latest_investor_flow=latest_flow,
            investor_flows=flows,
            flow_data_available=flow_data_available,
            flow_data_date=flow_data_date,
            flow_data_staleness_days=flow_data_staleness_days,
        )

    async def generate_and_log_signal(
        self,
        strategy: Strategy,
        symbol_code: str,
        strategy_version_id: int | None = None,
        strategy_params: dict | None = None,
        candle_cache: dict[str, list[MinuteCandle]] | None = None,
        market: str | None = None,
        exchange: str | None = None,
    ) -> SignalLog | None:
        # 같은 run에서 여러 전략이 동일 종목을 볼 때 캔들을 1회만 조회하도록 캐시한다.
        # (KIS 호출 수를 전략 수만큼 줄여 rate limit/지연을 완화)
        # market/exchange 인자(유니버스 종목별 라우팅)가 주어지면 전략 파라미터보다 우선한다.
        if candle_cache is not None and symbol_code in candle_cache:
            candles = candle_cache[symbol_code]
        else:
            params = strategy_params or {}
            candles = await self._market_data_service.get_recent_candles(
                symbol_code,
                timeframe=params.get("timeframe", "1m"),
                market=market or params.get("market", "KR"),
                exchange=exchange or params.get("exchange", "NAS"),
            )
            if candle_cache is not None:
                candle_cache[symbol_code] = candles

        # 신선도 가드: 장 마감/휴장으로 시세가 멈춰 캔들이 오래되면 신호를 만들지 않는다.
        # (KIS는 장이 끝났음을 알려주지 않고 마지막 캔들을 계속 돌려주므로 서버에서 판단)
        timeframe = (strategy_params or {}).get("timeframe", "1m")
        now = datetime.now(KST)
        max_staleness = get_settings().signal_max_candle_staleness_minutes
        if _is_candle_stale(candles, timeframe, now, max_staleness):
            age = _latest_candle_age_minutes(candles, now)
            logger.debug(
                "stale candle 가드: symbol=%s 최신 캔들이 %.0f분 전 — 신호 생성 건너뜀(장 마감/휴장 추정)",
                symbol_code, age if age is not None else -1,
            )
            await self._session.commit()
            return None

        context: StrategyContext | None = None
        if self._investor_flow_repo is not None and strategy_params:
            context = await self._build_strategy_context(symbol_code, candles, strategy_params)

        signal = strategy.generate_signal(symbol_code, candles, strategy_version_id, context=context)
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
