from decimal import Decimal

from app.trading.broker.schemas import MinuteCandle


def calculate_sma(candles: list[MinuteCandle], period: int) -> Decimal | None:
    """candles(오래된 순)의 마지막 period개 종가 단순이동평균(SMA)을 계산한다.

    데이터가 부족하면 None을 반환한다.
    """
    if len(candles) < period:
        return None
    closes = [c.close_price for c in candles[-period:]]
    return sum(closes, Decimal(0)) / period
