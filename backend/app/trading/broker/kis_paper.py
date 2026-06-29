from datetime import datetime, timedelta
from decimal import Decimal

from app.domain.models.enums import OrderStatus, TradeSide
from app.trading.broker.base import BrokerClient
from app.trading.broker.kis_client import KST, KISClientBase
from app.trading.broker.schemas import (
    AccountBalance,
    AccountHolding,
    AccountSummary,
    BrokerPositionItem,
    DailyCandle,
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
# tr_id: 국내주식기간별시세(일/주/월/년) — 일봉 OHLCV (M2.15B-2, read-only).
# ⚠ TODO(M2.15B-3): 라이브 사용 전 KIS 공식 문서로 경로/TR ID/응답 필드명을 반드시 재확인할 것.
#   (분봉 inquire-time-itemchartprice=FHKST03010200의 일봉 대응으로 inquire-daily-itemchartprice 사용.)
TR_ID_INQUIRE_DAILY_ITEMCHARTPRICE = "FHKST03010100"
# tr_id: 주식잔고조회 (모의투자)
TR_ID_INQUIRE_BALANCE = "VTTC8434R"
# tr_id: 주식잔고조회 (실전) — 향후 KISRealBrokerClient 구현 시 사용
TR_ID_INQUIRE_BALANCE_REAL = "TTTC8434R"
# tr_id: 주식 현금 매수 주문 (모의투자)
TR_ID_ORDER_CASH_BUY = "VTTC0012U"
# tr_id: 주식 현금 매도 주문 (모의투자)
TR_ID_ORDER_CASH_SELL = "VTTC0011U"
# tr_id: 주식일별주문체결조회 (모의투자, 3개월 이내) — KIS 문서 VTTC0081R
TR_ID_INQUIRE_DAILY_CCLD = "VTTC0081R"
# tr_id: 주식일별주문체결조회 (실전, 3개월 이내) — KIS 문서 TTTC0081R
# 향후 KISRealBrokerClient 구현 시 이 상수를 사용한다.
TR_ID_INQUIRE_DAILY_CCLD_REAL = "TTTC0081R"

# 일봉 페이지네이션(M2.15B-4). KIS 1회 ~100봉 한도 → end-date를 뒤로 옮기며 여러 페이지 호출.
MAX_DAILY_COUNT = 400          # 요청 count 방어적 상한(252+여유).
MAX_DAILY_PAGES = 8            # 페이지 수 하드 캡(무한 루프 방지).
DAILY_PAGE_LOOKBACK_DAYS = 200 # 페이지당 조회 윈도우(달력일). KIS가 윈도우 내 최신 ~100봉 반환.

# 결측/미체결 표기. KIS 일봉 결측은 "" 또는 "0"으로 올 수 있다.
_DAILY_MISSING = ("", None, ".")


def _parse_daily_row(row: dict) -> "DailyCandle | None":
    """KIS 일봉 output2 행 1개를 DailyCandle로 안전 파싱한다(실패 시 None).

    필드명은 KIS 일봉 차트 응답 기준(stck_bsop_date / stck_oprc·hgpr·lwpr·clpr / acml_vol /
    acml_tr_pbmn). 결측/비정상 행은 None을 반환해 건너뛴다.
    """
    bsop = row.get("stck_bsop_date")
    if bsop in _DAILY_MISSING:
        return None

    def _dec(key: str) -> "Decimal | None":
        v = row.get(key)
        if v in _DAILY_MISSING:
            return None
        try:
            return Decimal(str(v))
        except Exception:  # noqa: BLE001 - 비정상 숫자는 결측 처리
            return None

    o, h, lo, c = _dec("stck_oprc"), _dec("stck_hgpr"), _dec("stck_lwpr"), _dec("stck_clpr")
    if None in (o, h, lo, c):
        return None
    try:
        vol = int(row.get("acml_vol") or 0)
    except (TypeError, ValueError):
        vol = 0
    tv = _dec("acml_tr_pbmn")  # 거래대금(있으면), V1 저장엔 미사용
    return DailyCandle(
        business_date=str(bsop), open_price=o, high_price=h, low_price=lo,
        close_price=c, volume=vol, trading_value=tv,
    )

# 주문구분: 지정가
ORD_DVSN_LIMIT = "00"
# 거래소ID구분코드: KRX
EXCG_ID_DVSN_CD_KRX = "KRX"


class KISPaperBrokerClient(KISClientBase, BrokerClient):
    """KIS 모의투자(VTS) 서버를 사용하는 BrokerClient 구현체."""

    def __init__(self, *, account_no: str, market_div_code: str = MARKET_DIV_CODE_KRX, **kwargs) -> None:
        super().__init__(**kwargs)
        # account_no가 비어 있어도(.env 미설정) 앱이 기동되도록 관대하게 분리한다.
        # 실제 호출 시점에 KIS API가 인증 오류를 반환하게 된다.
        parts = account_no.split("-")
        self._cano = parts[0] if parts else ""
        self._acnt_prdt_cd = parts[1] if len(parts) > 1 else ""
        # 시세 분류 코드: J(KRX)/NX(NXT)/UN(통합). 연구용 시세 수집 범위만 바꾼다.
        # 주문은 항상 KRX(EXCG_ID_DVSN_CD_KRX)로 나간다(NXT 주문은 모의 미지원).
        self._market_div_code = market_div_code

    async def get_current_price(self, symbol_code: str) -> PriceQuote:
        data = await self._request(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            tr_id=TR_ID_INQUIRE_PRICE,
            params={
                "FID_COND_MRKT_DIV_CODE": self._market_div_code,
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
                "FID_COND_MRKT_DIV_CODE": self._market_div_code,
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

    async def _fetch_daily_page(
        self, symbol_code: str, start: datetime, end: datetime, adjusted: bool
    ) -> list[DailyCandle]:
        """단일 일봉 페이지([start, end] 윈도우)를 read-only로 조회·파싱한다.

        KIS는 1회 호출당 ~100봉(최신일 우선)만 반환한다. 결측/비정상 행은 skip. 주문 TR/place_order 미사용.
        """
        data = await self._request(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            tr_id=TR_ID_INQUIRE_DAILY_ITEMCHARTPRICE,
            params={
                "FID_COND_MRKT_DIV_CODE": self._market_div_code,
                "FID_INPUT_ISCD": symbol_code,
                "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
                "FID_INPUT_DATE_2": end.strftime("%Y%m%d"),
                "FID_PERIOD_DIV_CODE": "D",  # 일봉
                "FID_ORG_ADJ_PRC": "1" if adjusted else "0",  # 1=수정주가 0=원주가
            },
        )
        out: list[DailyCandle] = []
        for row in (data.get("output2") or []):
            candle = _parse_daily_row(row)
            if candle is not None:
                out.append(candle)
        return out

    async def get_daily_candles(
        self,
        symbol_code: str,
        start_date: "datetime | None" = None,
        end_date: "datetime | None" = None,
        count: int = 252,
        adjusted: bool = False,
    ) -> list[DailyCandle]:
        """일봉 OHLCV를 최대 `count`개 조회한다 (read-only · **주문 무관**).

        KIS 1회 ~100봉 한도를 넘어 `count`(예 252)를 채우려면 **end-date를 뒤로 옮기며 여러 페이지를
        호출**하고 business_date로 **dedupe**한다(M2.15B-4). 무한 루프 방지: 빈 페이지·진척 없음(가장 오래된
        날짜가 더 뒤로 안 감)·`MAX_DAILY_PAGES` 도달 시 중단. 최종 결과는 **business_date 내림차순(최신일 우선)**.
        ⚠ KIS 엔드포인트/필드명은 라이브 전 공식 문서로 재확인(M2.15B-3에서 동작 확인됨).
        """
        count = max(1, min(int(count), MAX_DAILY_COUNT))  # 방어적 상한
        overall_end = end_date or datetime.now(KST)
        floor = start_date  # 명시 시 하한(그 이전은 조회 안 함)

        collected: dict[str, DailyCandle] = {}
        cur_end = overall_end
        prev_oldest: str | None = None
        for _ in range(MAX_DAILY_PAGES):
            if floor is not None and cur_end < floor:
                break
            window_start = cur_end - timedelta(days=DAILY_PAGE_LOOKBACK_DAYS)
            if floor is not None and window_start < floor:
                window_start = floor
            page = await self._fetch_daily_page(symbol_code, window_start, cur_end, adjusted)
            if not page:
                break  # 빈 페이지 → 더 과거 데이터 없음
            for c in page:
                collected.setdefault(c.business_date, c)  # business_date dedupe
            oldest = min(c.business_date for c in page)
            if len(collected) >= count:
                break
            if prev_oldest is not None and oldest >= prev_oldest:
                break  # 진척 없음(무한 루프 방지)
            prev_oldest = oldest
            # 다음 페이지는 가장 오래된 거래일 직전에서 끝나도록.
            cur_end = datetime.strptime(oldest, "%Y%m%d").replace(tzinfo=KST) - timedelta(days=1)

        ordered = sorted(collected.values(), key=lambda c: c.business_date, reverse=True)
        return ordered[:count]

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

    async def get_broker_positions(self) -> list[BrokerPositionItem]:
        """KIS 모의투자 잔고조회 응답에서 BrokerPositionItem 목록을 반환한다.

        get_account_positions()와 동일한 KIS API를 호출하지만 BrokerPositionItem으로
        파싱해 sellable_quantity / purchase_amount 등 더 많은 필드를 제공한다.
        """
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
