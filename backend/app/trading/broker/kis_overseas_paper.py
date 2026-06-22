"""KIS 모의투자(VTS) 해외주식(미국장) 주문/잔고 BrokerClient 구현체 (Phase 2).

해외주식의 **주문/잔고/체결조회**는 모의투자(VTS) 도메인에서 지원된다
(VTTT/VTTS tr_id). 반면 **시세(현재가/분봉)** 는 모의 미지원이라 실전 도메인 전용이므로,
이 브로커는 시세 조회를 주입된 read-only `KISOverseasClient`(실전 도메인)에 위임한다.

안전:
    - 이 클래스는 **모의투자(VTS) 전용**이다. 실전 주문 tr_id(TTTT...)는 사용하지 않는다.
    - 실전 해외 주문은 별도 KISRealOverseasBrokerClient에서 real_trading_enabled 게이트와
      함께 구현되어야 한다(현재 미구현 — 실거래 비활성 불변식 유지).

참조: docs/kis-api 전체문서 — [해외주식] 주문/계좌
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.domain.models.enums import OrderStatus, TradeSide
from app.trading.broker.base import BrokerClient
from app.trading.broker.kis_client import KST, KISClientBase
from app.trading.broker.kis_overseas_client import KISOverseasClient
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

# tr_id: 해외주식 주문 — 모의투자 (미국)
# 매수/매도 모의 tr_id는 비대칭이다(KIS 문서: 매수 VTTT1002U, 매도 VTTT1001U).
TR_ID_US_ORDER_BUY = "VTTT1002U"
TR_ID_US_ORDER_SELL = "VTTT1001U"
# tr_id: 해외주식 주문 — 실전 (미국). 향후 KISRealOverseasBrokerClient에서 사용.
TR_ID_US_ORDER_BUY_REAL = "TTTT1002U"
TR_ID_US_ORDER_SELL_REAL = "TTTT1006U"
# tr_id: 해외주식 잔고 — 모의투자 / 실전
TR_ID_US_INQUIRE_BALANCE = "VTTS3012R"
TR_ID_US_INQUIRE_BALANCE_REAL = "TTTS3012R"
# tr_id: 해외주식 주문체결내역 — 모의투자 / 실전
TR_ID_US_INQUIRE_CCNL = "VTTS3035R"
TR_ID_US_INQUIRE_CCNL_REAL = "TTTS3035R"

# 주문구분: 지정가
ORD_DVSN_LIMIT = "00"
# 거래통화코드
TR_CRCY_CD_USD = "USD"

# 시세 EXCD(NAS/NYS/AMS) → 주문/잔고 OVRS_EXCG_CD(NASD/NYSE/AMEX) 매핑.
_EXCD_TO_OVRS_EXCG: dict[str, str] = {"NAS": "NASD", "NYS": "NYSE", "AMS": "AMEX"}
_DEFAULT_EXCD = "NAS"


def _to_ovrs_excg_cd(exchange: str | None) -> str:
    """KIS 시세 거래소 코드(EXCD)를 주문/잔고용 OVRS_EXCG_CD로 변환한다."""
    return _EXCD_TO_OVRS_EXCG.get((exchange or _DEFAULT_EXCD).upper(), "NASD")


class KISOverseasPaperBrokerClient(KISClientBase, BrokerClient):
    """KIS 모의투자(VTS) 서버로 미국 주식을 주문/조회하는 BrokerClient 구현체.

    시세(현재가/분봉)는 모의 미지원이므로 주입된 read-only `KISOverseasClient`(실전 도메인)에
    위임한다. quotes_client가 없으면 시세 메서드는 NotImplementedError를 발생시킨다.
    """

    def __init__(
        self,
        *,
        account_no: str,
        quotes_client: KISOverseasClient | None = None,
        default_exchange: str = _DEFAULT_EXCD,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        parts = account_no.split("-")
        self._cano = parts[0] if parts else ""
        self._acnt_prdt_cd = parts[1] if len(parts) > 1 else ""
        self._quotes = quotes_client
        self._default_exchange = default_exchange

    # ------------------------------------------------------------------ #
    # 시세 — 실전 도메인 read-only 클라이언트에 위임
    # ------------------------------------------------------------------ #
    async def get_current_price(self, symbol_code: str) -> PriceQuote:
        if self._quotes is None:
            raise NotImplementedError("해외 시세 클라이언트(quotes_client)가 구성되지 않았습니다.")
        return await self._quotes.get_overseas_price(symbol_code, exchange=self._default_exchange)

    async def get_minute_candles(
        self,
        symbol_code: str,
        target_time: str | None = None,
        include_past_data: bool = True,
    ) -> list[MinuteCandle]:
        if self._quotes is None:
            raise NotImplementedError("해외 시세 클라이언트(quotes_client)가 구성되지 않았습니다.")
        return await self._quotes.get_overseas_minute_candles(
            symbol_code, exchange=self._default_exchange, include_prev_day=include_past_data
        )

    # ------------------------------------------------------------------ #
    # 주문 — 모의투자(VTS) 도메인
    # ------------------------------------------------------------------ #
    async def place_order(self, order: OrderRequest) -> OrderResult:
        if order.order_type != OrderType.LIMIT:
            raise ValueError("MVP에서는 지정가(LIMIT) 주문만 지원합니다.")

        tr_id = TR_ID_US_ORDER_BUY if order.side == TradeSide.BUY else TR_ID_US_ORDER_SELL
        ovrs_excg_cd = _to_ovrs_excg_cd(order.exchange or self._default_exchange)

        data = await self._request(
            "POST",
            "/uapi/overseas-stock/v1/trading/order",
            tr_id=tr_id,
            json_body={
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "OVRS_EXCG_CD": ovrs_excg_cd,
                "PDNO": order.symbol_code,
                "ORD_QTY": str(order.quantity),
                "OVRS_ORD_UNPR": str(order.price),
                "ORD_SVR_DVSN_CD": "0",
                "ORD_DVSN": ORD_DVSN_LIMIT,
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

    # ------------------------------------------------------------------ #
    # 잔고 — 모의투자(VTS) 도메인
    # ------------------------------------------------------------------ #
    async def get_account_balance(self) -> AccountBalance:
        ovrs_excg_cd = _to_ovrs_excg_cd(self._default_exchange)
        data = await self._request(
            "GET",
            "/uapi/overseas-stock/v1/trading/inquire-balance",
            tr_id=TR_ID_US_INQUIRE_BALANCE,
            params={
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "OVRS_EXCG_CD": ovrs_excg_cd,
                "TR_CRCY_CD": TR_CRCY_CD_USD,
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": "",
            },
        )
        holdings = [
            AccountHolding(
                symbol_code=row["ovrs_pdno"],
                symbol_name=row.get("ovrs_item_name") or row["ovrs_pdno"],
                quantity=row["ovrs_cblc_qty"],
                avg_purchase_price=row["pchs_avg_pric"],
                current_price=row["now_pric2"],
                evaluation_amount=row["ovrs_stck_evlu_amt"],
                profit_loss_amount=row["frcr_evlu_pfls_amt"],
                profit_loss_rate=row["evlu_pfls_rt"],
            )
            for row in data.get("output1") or []
            if int(row.get("ovrs_cblc_qty") or 0) > 0
        ]
        summary_row = (data.get("output2") or {}) if isinstance(data.get("output2"), dict) else {}
        summary = AccountSummary(
            total_deposit=summary_row.get("frcr_pchs_amt1") or "0",
            total_purchase_amount=summary_row.get("frcr_pchs_amt1") or "0",
            total_evaluation_amount=summary_row.get("tot_evlu_pfls_amt") or "0",
            total_profit_loss_amount=summary_row.get("ovrs_tot_pfls") or "0",
        )
        return AccountBalance(holdings=holdings, summary=summary)

    async def get_account_positions(self) -> list[AccountHolding]:
        balance = await self.get_account_balance()
        return balance.holdings

    # ------------------------------------------------------------------ #
    # 체결내역 — 모의투자(VTS) 도메인
    # ------------------------------------------------------------------ #
    async def get_daily_executions(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> list[OrderExecution]:
        today = datetime.now(KST).strftime("%Y%m%d")
        start_date = start_date or today
        end_date = end_date or today

        data = await self._request(
            "GET",
            "/uapi/overseas-stock/v1/trading/inquire-ccnl",
            tr_id=TR_ID_US_INQUIRE_CCNL,
            params={
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "PDNO": "",
                "ORD_STRT_DT": start_date,
                "ORD_END_DT": end_date,
                "SLL_BUY_DVSN": "00",
                "CCLD_NCCS_DVSN": "00",
                # 모의투자계좌는 거래소 전체("") 조회만 가능
                "OVRS_EXCG_CD": "",
                "SORT_SQN": "DS",
                "ORD_DT": "",
                "ORD_GNO_BRNO": "",
                "ODNO": "",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": "",
            },
        )

        executions: list[OrderExecution] = []
        for row in data.get("output") or []:
            total_qty = int(row.get("ft_ord_qty") or row.get("ord_qty") or 0)
            filled_qty = int(row.get("ft_ccld_qty") or row.get("ccld_qty") or 0)
            unit_price = row.get("ft_ccld_unpr3") or row.get("ccld_unpr") or None
            filled_price = Decimal(unit_price) if filled_qty > 0 and unit_price else None
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
                    total_quantity=total_qty,
                    filled_quantity=filled_qty,
                    unfilled_quantity=int(row.get("nccs_qty") or 0),
                    filled_price=filled_price,
                    cancelled=row.get("prcs_stat_name") == "취소"
                    or row.get("ccld_yn") == "N" and row.get("cncl_yn") == "Y",
                    recorded_at=recorded_at,
                    raw=row,
                )
            )
        return executions
