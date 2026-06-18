"""C-2.13: KIS 실전투자 BrokerClient 구현체 (Read-Only 기본값).

실전 KIS OpenAPI 서버(https://openapi.koreainvestment.com:9443)를 사용한다.

안전 원칙:
  - real_trading_enabled=False (기본값)이면 place_order는 즉시 RealTradingDisabledError를 발생.
  - 잔고조회(TTTC8434R), 체결조회(TTTC0081R)는 read_only=True에서도 항상 허용.
  - KIS_REAL_TRADING_ENABLED=true를 명시하지 않으면 주문 불가.
  - 민감정보(app_key, app_secret, access_token, account_no)를 로그에 출력하지 않는다.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.domain.models.enums import OrderStatus, TradeSide
from app.trading.broker.base import BrokerClient
from app.trading.broker.exceptions import RealTradingDisabledError
from app.trading.broker.kis_client import KST, KISClientBase
from app.trading.broker.schemas import (
    AccountBalance,
    AccountHolding,
    AccountSummary,
    BrokerPositionItem,
    MinuteCandle,
    OrderExecution,
    OrderRequest,
    OrderResult,
    OrderType,
    PriceQuote,
)

# 실전 tr_id: 주식잔고조회
TR_ID_INQUIRE_BALANCE_REAL = "TTTC8434R"
# 실전 tr_id: 주식일별주문체결조회
TR_ID_INQUIRE_DAILY_CCLD_REAL = "TTTC0081R"
# 실전 tr_id: 주식 현금 매수 주문
TR_ID_ORDER_CASH_BUY_REAL = "TTTC0012U"
# 실전 tr_id: 주식 현금 매도 주문
TR_ID_ORDER_CASH_SELL_REAL = "TTTC0011U"

# 모의/실전 공통 tr_id
TR_ID_INQUIRE_PRICE = "FHKST01010100"
TR_ID_INQUIRE_TIME_ITEMCHARTPRICE = "FHKST03010200"

MARKET_DIV_CODE_KRX = "J"
ORD_DVSN_LIMIT = "00"
EXCG_ID_DVSN_CD_KRX = "KRX"


class KISRealBrokerClient(KISClientBase, BrokerClient):
    """KIS 실전투자 서버를 사용하는 BrokerClient 구현체.

    기본값(real_trading_enabled=False)에서는 read-only 모드로 동작한다.
    잔고조회·체결조회만 허용되며, place_order 호출 시 RealTradingDisabledError가 발생한다.

    실전 주문을 활성화하려면 KIS_REAL_TRADING_ENABLED=true를 설정해야 한다.
    이 결정은 사람이 명시적으로 내려야 하며, 자동화 코드가 이 값을 변경해서는 안 된다.
    """

    def __init__(self, *, account_no: str, real_trading_enabled: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        parts = account_no.split("-")
        self._cano = parts[0] if parts else ""
        self._acnt_prdt_cd = parts[1] if len(parts) > 1 else ""
        self.real_trading_enabled: bool = real_trading_enabled

    async def get_current_price(self, symbol_code: str) -> PriceQuote:
        data = await self._request(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            tr_id=TR_ID_INQUIRE_PRICE,
            params={
                "FID_COND_MRKT_DIV_CODE": MARKET_DIV_CODE_KRX,
                "FID_INPUT_ISCD": symbol_code,
            },
        )
        output = data["output"]
        return PriceQuote(
            symbol_code=symbol_code,
            current_price=output["stck_prpr"],
            change=output["prdy_vrss"],
            change_rate=output["prdy_ctrt"],
            open_price=output["stck_oprc"],
            high_price=output["stck_hgpr"],
            low_price=output["stck_lwpr"],
            volume=output["acml_vol"],
        )

    async def get_minute_candles(
        self,
        symbol_code: str,
        target_time: str | None = None,
        include_past_data: bool = True,
    ) -> list[MinuteCandle]:
        if target_time is None:
            target_time = datetime.now(KST).strftime("%H%M%S")

        data = await self._request(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
            tr_id=TR_ID_INQUIRE_TIME_ITEMCHARTPRICE,
            params={
                "FID_COND_MRKT_DIV_CODE": MARKET_DIV_CODE_KRX,
                "FID_INPUT_ISCD": symbol_code,
                "FID_INPUT_HOUR_1": target_time,
                "FID_PW_DATA_INCU_YN": "Y" if include_past_data else "N",
                "FID_ETC_CLS_CODE": "",
            },
        )
        return [
            MinuteCandle(
                business_date=row["stck_bsop_date"],
                trade_time=row["stck_cntg_hour"],
                open_price=row["stck_oprc"],
                high_price=row["stck_hgpr"],
                low_price=row["stck_lwpr"],
                close_price=row["stck_prpr"],
                volume=row["cntg_vol"],
            )
            for row in data["output2"]
        ]

    async def get_account_balance(self) -> AccountBalance:
        data = await self._request(
            "GET",
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            tr_id=TR_ID_INQUIRE_BALANCE_REAL,
            params={
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )
        holdings = [
            AccountHolding(
                symbol_code=row["pdno"],
                symbol_name=row["prdt_name"],
                quantity=row["hldg_qty"],
                avg_purchase_price=row["pchs_avg_pric"],
                current_price=row["prpr"],
                evaluation_amount=row["evlu_amt"],
                profit_loss_amount=row["evlu_pfls_amt"],
                profit_loss_rate=row["evlu_pfls_rt"],
            )
            for row in data["output1"]
            if int(row["hldg_qty"]) > 0
        ]
        summary_row = data["output2"][0]
        summary = AccountSummary(
            total_deposit=summary_row["dnca_tot_amt"],
            total_purchase_amount=summary_row["pchs_amt_smtl_amt"],
            total_evaluation_amount=summary_row["tot_evlu_amt"],
            total_profit_loss_amount=summary_row["evlu_pfls_smtl_amt"],
        )
        return AccountBalance(holdings=holdings, summary=summary)

    async def get_account_positions(self) -> list[AccountHolding]:
        balance = await self.get_account_balance()
        return balance.holdings

    async def place_order(self, order: OrderRequest) -> OrderResult:
        """실전 주문 실행.

        real_trading_enabled=False(기본값)이면 즉시 RealTradingDisabledError를 발생시킨다.
        TradeService.execute_signal()도 이 브로커의 real_trading_enabled를 사전 확인하므로,
        이 method는 defense-in-depth 레이어다.
        """
        if not self.real_trading_enabled:
            raise RealTradingDisabledError(
                "실전 주문이 비활성화되어 있습니다 (real_trading_enabled=False). "
                "KIS_REAL_TRADING_ENABLED=true를 설정해야 실전 주문이 가능합니다. "
                "이 설정은 사람이 명시적으로 변경해야 합니다."
            )

        if order.order_type != OrderType.LIMIT:
            raise ValueError("MVP에서는 지정가(LIMIT) 주문만 지원합니다.")

        tr_id = TR_ID_ORDER_CASH_BUY_REAL if order.side == TradeSide.BUY else TR_ID_ORDER_CASH_SELL_REAL

        data = await self._request(
            "POST",
            "/uapi/domestic-stock/v1/trading/order-cash",
            tr_id=tr_id,
            json_body={
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "PDNO": order.symbol_code,
                "ORD_DVSN": ORD_DVSN_LIMIT,
                "ORD_QTY": str(order.quantity),
                "ORD_UNPR": str(order.price),
                "EXCG_ID_DVSN_CD": EXCG_ID_DVSN_CD_KRX,
                "SLL_TYPE": "" if order.side == TradeSide.BUY else "01",
                "CNDT_PRIC": "",
            },
            retryable=False,
        )
        output = data["output"]
        return OrderResult(
            broker_order_id=output["ODNO"],
            org_no=output.get("KRX_FWDG_ORD_ORGNO"),
            order_status=OrderStatus.PENDING,
            ordered_at=datetime.now(KST),
        )

    async def get_broker_positions(self) -> list[BrokerPositionItem]:
        data = await self._request(
            "GET",
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            tr_id=TR_ID_INQUIRE_BALANCE_REAL,
            params={
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )
        return [
            BrokerPositionItem(
                symbol_code=row["pdno"],
                symbol_name=row["prdt_name"],
                quantity=int(row["hldg_qty"]),
                sellable_quantity=int(row["ord_psbl_qty"]),
                average_price=Decimal(row["pchs_avg_pric"]),
                purchase_amount=Decimal(row["pchs_amt"]),
                current_price=Decimal(row["prpr"]),
                market_value=Decimal(row["evlu_amt"]),
                unrealized_pnl=Decimal(row["evlu_pfls_amt"]),
                pnl_rate=Decimal(row["evlu_pfls_rt"]),
            )
            for row in data["output1"]
            if int(row["hldg_qty"]) > 0
        ]

    async def get_daily_executions(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> list[OrderExecution]:
        today = datetime.now(KST).strftime("%Y%m%d")
        if start_date is None:
            start_date = today
        if end_date is None:
            end_date = today

        data = await self._request(
            "GET",
            "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
            tr_id=TR_ID_INQUIRE_DAILY_CCLD_REAL,
            params={
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "INQR_STRT_DT": start_date,
                "INQR_END_DT": end_date,
                "SLL_BUY_DVSN_CD": "00",
                "INQR_DVSN": "00",
                "PDNO": "",
                "CCLD_DVSN": "00",
                "ORD_GNO_BRNO": "",
                "ODNO": "",
                "INQR_DVSN_3": "00",
                "INQR_DVSN_1": "",
                "EXCG_ID_DVSN_CD": EXCG_ID_DVSN_CD_KRX,
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )

        executions = []
        for row in data["output1"]:
            filled_quantity = int(row["tot_ccld_qty"])
            filled_price = (
                Decimal(row["avg_prvs"])
                if filled_quantity > 0 and row.get("avg_prvs")
                else None
            )
            recorded_at = None
            if row.get("ord_dt") and row.get("ord_tmd"):
                recorded_at = datetime.strptime(
                    f"{row['ord_dt']}{row['ord_tmd']}", "%Y%m%d%H%M%S"
                ).replace(tzinfo=KST)

            executions.append(
                OrderExecution(
                    broker_order_id=row["odno"],
                    org_no=row.get("ord_gno_brno"),
                    symbol_code=row.get("pdno"),
                    sll_buy_dvsn_cd=row.get("sll_buy_dvsn_cd"),
                    unfilled_quantity=int(row["rmn_qty"]) if row.get("rmn_qty") else 0,
                    total_quantity=int(row["ord_qty"]),
                    filled_quantity=filled_quantity,
                    filled_price=filled_price,
                    cancelled=row.get("cncl_yn") == "Y",
                    recorded_at=recorded_at,
                    raw=row,
                )
            )
        return executions
