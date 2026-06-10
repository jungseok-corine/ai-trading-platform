from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.trading.broker.schemas import MinuteCandle

KST = ZoneInfo("Asia/Seoul")


def calculate_sma(candles: list[MinuteCandle], period: int) -> Decimal | None:
    """candles(오래된 순)의 마지막 period개 종가 단순이동평균(SMA)을 계산한다.

    데이터가 부족하면 None을 반환한다.
    """
    if len(candles) < period:
        return None
    closes = [c.close_price for c in candles[-period:]]
    return sum(closes, Decimal(0)) / period


def candle_timestamp(candle: MinuteCandle) -> datetime:
    """분봉의 business_date + trade_time을 KST datetime으로 변환한다."""
    return datetime.strptime(
        f"{candle.business_date}{candle.trade_time}", "%Y%m%d%H%M%S"
    ).replace(tzinfo=KST)
