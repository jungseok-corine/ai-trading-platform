"""SEC EDGAR 공시 수집 API (C-5.20).

보유/관심 US 종목의 중요 공시(8-K/10-K/10-Q 등)를 가져와 news_events에 저장한다(중요도
미달은 제외). read-only 수집이며 주문과 무관하다. User-Agent 미설정이면 422.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.edgar_ingest_service import EdgarIngestService
from app.services.edgar_provider import EdgarProviderError

router = APIRouter(prefix="/edgar", tags=["edgar"])


def get_service(session: AsyncSession = Depends(get_db)) -> EdgarIngestService:
    return EdgarIngestService(session)


class EdgarIngestRequest(BaseModel):
    # None이면 enabled watchlist의 US 종목을 모니터 대상으로 한다.
    symbols: list[str] | None = None
    since_days: int = 2


class EdgarIngestSummaryRead(BaseModel):
    fetched: int
    matched: int
    material: int
    created: int
    skipped_existing: int
    resolved: int
    unresolved: list[str]


@router.post("/ingest", response_model=EdgarIngestSummaryRead)
async def ingest_filings(
    payload: EdgarIngestRequest,
    service: EdgarIngestService = Depends(get_service),
) -> EdgarIngestSummaryRead:
    """최근 SEC 공시를 가져와 모니터 US 종목·유형 중요도로 필터해 저장한다."""
    try:
        summary = await service.ingest(
            symbols=payload.symbols, since_days=payload.since_days
        )
    except EdgarProviderError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return EdgarIngestSummaryRead(**summary.to_dict())
