from datetime import datetime
from decimal import Decimal

from app.domain.models.enums import OrderStatus, TradeSide
from app.trading.broker.base import BrokerClient
from app.trading.broker.kis_client import KST, KISClientBase
from app.trading.broker.schemas import (
    AccountBalance,
    AccountHolding,
    AccountSummary,
    MinuteCandle,
    OrderExecution,
    OrderRequest,
    OrderResult,
    OrderType,
    PriceQuote,
)

# 국내 주식/ETF/ETN 조건 시장 분류 코드
MARKET_DIV_CODE_KRX = "J"

# tr_id: 주식현재가 시세 (실전/모의 동일)
TR_ID_INQUIRE_PRICE = "FHKST01010100"
# tr_id: 주식당일분봉조회 (실전/모의 동일)
TR_ID_INQUIRE_TIME_ITEMCHARTPRICE = "FHKST03010200"
# tr_id: 주식잔고조회 (모의투자)
TR_ID_INQUIRE_BALANCE = "VTTC8434R"
# tr_id: 주식 현금 매수 주문 (모의투자)
TR_ID_ORDER_CASH_BUY = "VTTC0012U"
# tr_id: 주식 현금 매도 주문 (모의투자)
TR_ID_ORDER_CASH_SELL = "VTTC0011U"
# tr_id: 주식일별주문체결조회 (모의투자, 3개월 이내) — KIS 문서 VTTC0081R
TR_ID_INQUIRE_DAILY_CCLD = "VTTC0081R"
# tr_id: 주식일별주문체결조회 (실전, 3개월 이내) — KIS 문서 TTTC0081R
# 향후 KISRealBrokerClient 구현 시 이 상수를 사용한다.
TR_ID_INQUIRE_DAILY_CCLD_REAL = "TTTC0081R"

# 주문구분: 지정가
ORD_DVSN_LIMIT = "00"
# 거래소ID구분코드: KRX
EXCG_ID_DVSN_CD_KRX = "KRX"


class KISPaperBrokerClient(KISClientBase, BrokerClient):
    """KIS 모의투자(VTS) 서버를 사용하는 BrokerClient 구현체."""

    def __init__(self, *, account_no: str, **kwargs) -> None:
        super().__init__(**kwargs)
        # account_no가 비어 있어도(.env 미설정) 앱이 기동되도록 관대하게 분리한다.
        # 실제 호출 시점에 KIS API가 인증 오류를 반환하게 된다.
        parts = account_no.split("-")
        self._cano = parts[0] if parts else ""
        self._acnt_prdt_cd = parts[1] if len(parts) > 1 else ""

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
            tr_id=TR_ID_INQUIRE_BALANCE,
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
        """KIS 모의투자 잔고조회(inquire-balance) 응답의 보유종목 목록을 반환한다."""
        balance = await self.get_account_balance()
        return balance.holdings

    async def place_order(self, order: OrderRequest) -> OrderResult:
        if order.order_type != OrderType.LIMIT:
            raise ValueError("MVP에서는 지정가(LIMIT) 주문만 지원합니다.")

        tr_id = TR_ID_ORDER_CASH_BUY if order.side == TradeSide.BUY else TR_ID_ORDER_CASH_SELL

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
            retryable=False,  # 중복주문 방지 — 주문 API는 재시도하지 않는다
        )
        output = data["output"]
        return OrderResult(
            broker_order_id=output["ODNO"],
            org_no=output.get("KRX_FWDG_ORD_ORGNO"),
            order_status=OrderStatus.PENDING,
            ordered_at=datetime.now(KST),
        )

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
            tr_id=TR_ID_INQUIRE_DAILY_CCLD,
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
            filled_price = Decimal(row["avg_prvs"]) if filled_quantity > 0 and row.get("avg_prvs") else None
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
