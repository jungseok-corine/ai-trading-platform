"""수급 데이터 자동 수집 API (C-2.34).

watchlist 종목(또는 지정 종목)의 투자자 수급 데이터를 KIS에서 가져와 DB에 채운다.
read-only market data 수집이며 주문과 무관하다.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.data_refresh_service import DataRefreshService
from app.services.investor_flow_service import InvestorFlowService

router = APIRouter(prefix="/data-refresh", tags=["data-refresh"])


def get_data_refresh_service(
    request: Request, session: AsyncSession = Depends(get_db)
) -> DataRefreshService:
    client = getattr(request.app.state, "investor_flow_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="investor_flow_client not initialized")
    flow_service = InvestorFlowService(session=session, client=client)
    return DataRefreshService(session, flow_service)


class RefreshRequest(BaseModel):
    # None이면 enabled watchlist의 enabled 종목 전체를 대상으로 한다.
    symbol_codes: list[str] | None = None
    date_from: date | None = None
    date_to: date | None = None


class RefreshResponse(BaseModel):
    requested: int
    succeeded: int
    failed: int
    rows: int
    errors: dict[str, str]


@router.post("/investor-flows", response_model=RefreshResponse)
async def refresh_investor_flows(
    payload: RefreshRequest,
    service: DataRefreshService = Depends(get_data_refresh_service),
) -> RefreshResponse:
    symbols = payload.symbol_codes
    if symbols is None:
        symbols = await service.watchlist_symbols()
    summary = await service.refresh_investor_flows(
        symbols, date_from=payload.date_from, date_to=payload.date_to
    )
    return RefreshResponse(
        requested=summary.requested,
        succeeded=summary.succeeded,
        failed=summary.failed,
        rows=summary.rows,
        errors=summary.errors,
    )
