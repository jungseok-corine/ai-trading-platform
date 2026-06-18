"""KIS 투자자별 수급 데이터 조회 전용 클라이언트.

TR_ID FHPTJ04160001 (종목별 투자자매매동향 일별)은 KIS 실전 도메인 전용이다.
모의투자(VTS) 도메인은 해당 API를 지원하지 않는다.

이 클라이언트는 주문 API를 일절 포함하지 않는 read-only 클라이언트다.
"""
import logging
from datetime import date

from app.trading.broker.kis_client import KISClientBase

logger = logging.getLogger(__name__)

# TR_ID: 종목별 투자자매매동향(일별) — 실전 전용, 모의투자 미지원
TR_ID_INVESTOR_TRADE_BY_STOCK_DAILY = "FHPTJ04160001"

# KRX 시장 구분 코드
MARKET_DIV_CODE_KRX = "J"


class KISInvestorFlowClient(KISClientBase):
    """KIS 실전 도메인을 통해 투자자 수급 데이터를 조회하는 read-only 클라이언트.

    모의투자(VTS) 도메인은 투자자 수급 API를 지원하지 않으므로,
    이 클라이언트는 항상 실전 도메인 URL과 실전 자격증명을 사용해야 한다.
    주문(place_order) 메서드는 존재하지 않는다.
    """

    async def get_daily_investor_flow_by_stock(
        self,
        symbol_code: str,
        target_date: date,
    ) -> list[dict]:
        """종목별 일별 투자자매매동향(FHPTJ04160001)을 조회한다.

        반환: output2 배열 (영업일 단위 투자자별 순매수 데이터).
        금액 단위: 백만원. 수량 단위: 주.
        당일 데이터는 장 종료 후 15:40 이후부터 조회 가능하다.

        Raises:
            KISAPIError: KIS API가 rt_cd != '0' 응답을 반환할 때.
        """
        date_str = target_date.strftime("%Y%m%d")
        logger.debug(
            "투자자 수급 조회: symbol=%s date=%s", symbol_code, date_str
        )
        data = await self._request(
            "GET",
            "/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily",
            tr_id=TR_ID_INVESTOR_TRADE_BY_STOCK_DAILY,
            params={
                "FID_COND_MRKT_DIV_CODE": MARKET_DIV_CODE_KRX,
                "FID_INPUT_ISCD": symbol_code,
                "FID_INPUT_DATE_1": date_str,
                "FID_ORG_ADJ_PRC": "",
                "FID_ETC_CLS_CODE": "1",
            },
        )
        rows = data.get("output2") or []
        logger.debug("수급 데이터 %d건 수신: symbol=%s", len(rows), symbol_code)
        return rows
