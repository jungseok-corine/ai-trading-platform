"""투자자 수급 데이터 API (C-2.18).

GET  /api/v1/investor-flows         — 저장된 수급 데이터 조회
POST /api/v1/investor-flows/fetch   — KIS에서 수급 데이터를 가져와 저장

두 엔드포인트 모두 read-only market data 조회/수집이며 주문과 무관하다.
KIS_REAL_TRADING_ENABLED 설정과 독립적으로 동작한다.
"""
import logging
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.investor_flow_service import InvestorFlowService
from app.trading.broker.exceptions import KISAPIError
from app.trading.broker.kis_investor_flow_client import KISInvestorFlowClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/investor-flows", tags=["investor-flows"])


def _get_investor_flow_client(request: Request) -> KISInvestorFlowClient:
    client = getattr(request.app.state, "investor_flow_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="investor_flow_client not initialized")
    return client


def _get_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> InvestorFlowService:
    client = _get_investor_flow_client(request)
    return InvestorFlowService(session=session, client=client)


class InvestorFlowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol_code: str
    trade_date: date
    foreign_net_buy_quantity: int | None
    foreign_net_buy_amount: Decimal | None
    institution_net_buy_quantity: int | None
    institution_net_buy_amount: Decimal | None
    individual_net_buy_quantity: int | None
    individual_net_buy_amount: Decimal | None
    source: str


class InvestorFlowFetchRequest(BaseModel):
    symbol_code: str
    date_from: date
    date_to: date


class InvestorFlowFetchResponse(BaseModel):
    symbol_code: str
    date_from: date
    date_to: date
    stored_count: int
    flows: list[InvestorFlowRead]


@router.get("", response_model=list[InvestorFlowRead])
async def list_investor_flows(
    symbol_code: str = Query(..., description="종목코드 (예: 005930)"),
    date_from: date | None = Query(None, description="조회 시작일 (YYYY-MM-DD)"),
    date_to: date | None = Query(None, description="조회 종료일 (YYYY-MM-DD)"),
    service: InvestorFlowService = Depends(_get_service),
) -> list[InvestorFlowRead]:
    """저장된 투자자 수급 데이터를 날짜 범위로 조회한다 (최신 날짜 순).

    데이터가 없으면 빈 배열([])을 반환한다.
    """
    flows = await service.list_by_symbol(symbol_code, date_from, date_to)
    return [InvestorFlowRead.model_validate(f) for f in flows]


@router.post("/fetch", response_model=InvestorFlowFetchResponse)
async def fetch_investor_flows(
    payload: InvestorFlowFetchRequest,
    service: InvestorFlowService = Depends(_get_service),
) -> InvestorFlowFetchResponse:
    """KIS 실전 API에서 투자자 수급 데이터를 가져와 DB에 저장한다.

    동일 (symbol_code, trade_date)가 이미 존재하면 최신 데이터로 갱신(upsert)한다.
    주문 API를 호출하지 않는다.

    Raises:
        400: date_from > date_to인 경우.
        502: KIS API 호출 실패 (인증 오류, rate limit 등).
    """
    if payload.date_from > payload.date_to:
        raise HTTPException(status_code=400, detail="date_from must be <= date_to")

    try:
        stored = await service.fetch_and_store(
            payload.symbol_code, payload.date_from, payload.date_to
        )
    except KISAPIError as exc:
        logger.warning("KIS 수급 조회 실패: symbol=%s err=%s", payload.symbol_code, exc.msg_cd)
        raise HTTPException(status_code=502, detail=f"KIS API 오류: {exc.msg_cd}") from exc

    return InvestorFlowFetchResponse(
        symbol_code=payload.symbol_code,
        date_from=payload.date_from,
        date_to=payload.date_to,
        stored_count=len(stored),
        flows=[InvestorFlowRead.model_validate(f) for f in stored],
    )
