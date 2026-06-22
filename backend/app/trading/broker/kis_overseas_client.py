"""KIS 해외주식(미국장) 시세 조회 전용 클라이언트.

해외주식 분봉(HHDFS76950200)은 KIS 실전 도메인 전용이며, 모의투자(VTS)는 미지원이다.
따라서 이 클라이언트는 항상 실전 도메인 URL과 실전 자격증명을 사용하는 **read-only** 시세
클라이언트다. 주문(place_order) 메서드는 일절 포함하지 않는다.

참조: docs/kis-api/overseas-endpoints.md
"""
import logging

from app.trading.broker.kis_client import KISClientBase
from app.trading.broker.schemas import MinuteCandle

logger = logging.getLogger(__name__)

# TR_ID: 해외주식 분봉조회 — 실전 전용, 모의투자 미지원
TR_ID_OVERSEAS_TIME_ITEMCHARTPRICE = "HHDFS76950200"

# 미국 거래소 코드 (EXCD)
US_EXCHANGES = frozenset({"NAS", "NYS", "AMS"})
_DEFAULT_EXCHANGE = "NAS"


class KISOverseasClient(KISClientBase):
    """KIS 실전 도메인을 통해 해외주식 시세를 조회하는 read-only 클라이언트.

    분봉 시세는 모의 미지원이므로 실전 도메인+실전 키로만 동작한다.
    주문 메서드는 존재하지 않는다(시세 전용).
    """

    async def get_overseas_minute_candles(
        self,
        symbol_code: str,
        exchange: str = _DEFAULT_EXCHANGE,
        nmin: int = 5,
        n_records: int = 120,
        include_prev_day: bool = True,
    ) -> list[MinuteCandle]:
        """해외주식 분봉(HHDFS76950200)을 공통 MinuteCandle 리스트로 조회한다.

        Args:
            symbol_code: 종목 티커 (ex. "AAPL", "TSLA")
            exchange: 거래소 코드 EXCD (NAS/NYS/AMS)
            nmin: 분갭 (5=5분봉)
            n_records: 요청 개수 (최대 120)
            include_prev_day: 전일 포함 여부(PINC)

        반환 캔들은 한국시간 기준(business_date=kymd, trade_time=khms)으로 매핑된다.

        Raises:
            KISAPIError: KIS API가 rt_cd != '0' 응답을 반환할 때.
        """
        logger.debug(
            "해외 분봉 조회: exchange=%s symbol=%s nmin=%s", exchange, symbol_code, nmin
        )
        data = await self._request(
            "GET",
            "/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice",
            tr_id=TR_ID_OVERSEAS_TIME_ITEMCHARTPRICE,
            params={
                "AUTH": "",
                "EXCD": exchange,
                "SYMB": symbol_code,
                "NMIN": str(nmin),
                "PINC": "1" if include_prev_day else "0",
                "NEXT": "",
                "NREC": str(min(n_records, 120)),
                "FILL": "",
                "KEYB": "",
            },
        )
        rows = data.get("output2") or []
        candles = [
            MinuteCandle(
                business_date=row["kymd"],
                trade_time=row["khms"],
                open_price=row["open"],
                high_price=row["high"],
                low_price=row["low"],
                close_price=row["last"],
                volume=row["evol"],
            )
            for row in rows
        ]
        # 전략은 "오래된 순(과거→현재)"을 기대하므로 한국기준 일자+시간으로 오름차순 정렬한다.
        candles.sort(key=lambda c: (c.business_date, c.trade_time))
        logger.debug("해외 분봉 %d건 수신: symbol=%s", len(candles), symbol_code)
        return candles
