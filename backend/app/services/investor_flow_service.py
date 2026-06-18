"""투자자 수급 데이터 수집/저장/조회 서비스 (C-2.18).

KIS 실전 도메인 전용 API(FHPTJ04160001)를 통해 종목별 일별 투자자 수급을 수집한다.
이 서비스는 read-only market data 수집 전용이며 주문 로직과 무관하다.
"""
import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.investor_flow import InvestorFlow
from app.trading.broker.kis_investor_flow_client import KISInvestorFlowClient

logger = logging.getLogger(__name__)

_SOURCE = "kis"


def _safe_int(value: str | None) -> int | None:
    """KIS 응답 숫자 문자열을 int로 변환한다. 빈 값이나 파싱 실패 시 None."""
    if not value or value.strip() == "":
        return None
    try:
        return int(value.strip().replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _safe_decimal(value: str | None) -> Decimal | None:
    """KIS 응답 숫자 문자열을 Decimal로 변환한다. 빈 값이나 파싱 실패 시 None."""
    if not value or value.strip() == "":
        return None
    try:
        return Decimal(value.strip().replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


def parse_investor_flow_row(symbol_code: str, row: dict) -> dict:
    """KIS output2 한 행을 DB 저장 가능한 dict로 변환한다.

    필드:
      stck_bsop_date  → trade_date (YYYYMMDD → date)
      frgn_ntby_qty   → foreign_net_buy_quantity (주, 음수=순매도)
      frgn_ntby_tr_pbmn → foreign_net_buy_amount (백만원)
      orgn_ntby_qty   → institution_net_buy_quantity
      orgn_ntby_tr_pbmn → institution_net_buy_amount
      prsn_ntby_qty   → individual_net_buy_quantity
      prsn_ntby_tr_pbmn → individual_net_buy_amount
    """
    date_str = row.get("stck_bsop_date", "")
    if len(date_str) != 8:
        raise ValueError(f"stck_bsop_date 형식 오류: {date_str!r}")

    trade_date = date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))

    return {
        "symbol_code": symbol_code,
        "trade_date": trade_date,
        "foreign_net_buy_quantity": _safe_int(row.get("frgn_ntby_qty")),
        "foreign_net_buy_amount": _safe_decimal(row.get("frgn_ntby_tr_pbmn")),
        "institution_net_buy_quantity": _safe_int(row.get("orgn_ntby_qty")),
        "institution_net_buy_amount": _safe_decimal(row.get("orgn_ntby_tr_pbmn")),
        "individual_net_buy_quantity": _safe_int(row.get("prsn_ntby_qty")),
        "individual_net_buy_amount": _safe_decimal(row.get("prsn_ntby_tr_pbmn")),
        "raw_payload": dict(row),
        "source": _SOURCE,
    }


class InvestorFlowService:
    """투자자 수급 데이터 수집/저장/조회 서비스."""

    def __init__(self, session: AsyncSession, client: KISInvestorFlowClient) -> None:
        self._session = session
        self._client = client

    async def fetch_and_store(
        self,
        symbol_code: str,
        date_from: date,
        date_to: date,
    ) -> list[InvestorFlow]:
        """KIS에서 date_from~date_to 범위의 수급 데이터를 가져와 upsert한다.

        동일 (symbol_code, trade_date, source) 조합이 이미 존재하면 numeric 필드와
        raw_payload를 갱신한다. 신규 행이면 삽입한다.

        KIS API는 날짜 하나 당 output2 배열로 다수의 날짜 데이터를 반환하므로,
        date_from~date_to 범위를 하루씩 조회하지 않고 date_to 기준 1회 조회 후
        반환된 배열에서 date_from 이상인 행만 저장한다.

        Returns:
            저장/갱신된 InvestorFlow 행 목록.
        """
        rows = await self._client.get_daily_investor_flow_by_stock(symbol_code, date_to)
        if not rows:
            logger.info("수급 데이터 없음: symbol=%s date_to=%s", symbol_code, date_to)
            return []

        stored_dates: list[date] = []
        for row in rows:
            try:
                parsed = parse_investor_flow_row(symbol_code, row)
            except (ValueError, KeyError) as exc:
                logger.warning("수급 row 파싱 실패: symbol=%s err=%s", symbol_code, exc)
                continue

            if not (date_from <= parsed["trade_date"] <= date_to):
                continue

            stmt = (
                pg_insert(InvestorFlow)
                .values(**parsed)
                .on_conflict_do_update(
                    constraint="uq_investor_flows_symbol_date_source",
                    set_={
                        "foreign_net_buy_quantity": parsed["foreign_net_buy_quantity"],
                        "foreign_net_buy_amount": parsed["foreign_net_buy_amount"],
                        "institution_net_buy_quantity": parsed["institution_net_buy_quantity"],
                        "institution_net_buy_amount": parsed["institution_net_buy_amount"],
                        "individual_net_buy_quantity": parsed["individual_net_buy_quantity"],
                        "individual_net_buy_amount": parsed["individual_net_buy_amount"],
                        "raw_payload": parsed["raw_payload"],
                        "updated_at": func.now(),
                    },
                )
            )
            await self._session.execute(stmt)
            stored_dates.append(parsed["trade_date"])

        await self._session.commit()
        # expire_on_commit=False 설정 시 commit 후에도 identity map에 이전 값이 남아 있으므로
        # 명시적으로 만료 후 DB에서 재조회한다.
        self._session.expire_all()

        if not stored_dates:
            return []

        # commit 후 fresh query로 최신 DB 상태를 반환
        fresh = await self._session.execute(
            select(InvestorFlow)
            .where(InvestorFlow.symbol_code == symbol_code)
            .where(InvestorFlow.trade_date.in_(stored_dates))
            .order_by(InvestorFlow.trade_date.desc())
        )
        result_rows = list(fresh.scalars().all())
        logger.info("수급 데이터 저장 완료: symbol=%s count=%d", symbol_code, len(result_rows))
        return result_rows

    async def list_by_symbol(
        self,
        symbol_code: str,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[InvestorFlow]:
        """종목 코드와 날짜 범위로 수급 데이터를 조회한다 (최신 날짜 순)."""
        stmt = (
            select(InvestorFlow)
            .where(InvestorFlow.symbol_code == symbol_code)
            .order_by(InvestorFlow.trade_date.desc())
        )
        if date_from:
            stmt = stmt.where(InvestorFlow.trade_date >= date_from)
        if date_to:
            stmt = stmt.where(InvestorFlow.trade_date <= date_to)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def latest_by_symbol(self, symbol_code: str) -> InvestorFlow | None:
        """종목의 가장 최근 수급 데이터 1건을 반환한다."""
        stmt = (
            select(InvestorFlow)
            .where(InvestorFlow.symbol_code == symbol_code)
            .order_by(InvestorFlow.trade_date.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
