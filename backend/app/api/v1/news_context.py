"""뉴스/미국장 맥락 API (C-2.28).

뉴스 이벤트와 미국장 일별 스냅샷을 저장·조회한다. 모두 메타데이터 작업이며 주문과 무관하다.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import MarketCode
from app.services.news_context_service import NewsContextService

router = APIRouter(tags=["news-context"])


def get_service(session: AsyncSession = Depends(get_db)) -> NewsContextService:
    return NewsContextService(session)


# --- news ------------------------------------------------------------------
class NewsCreateRequest(BaseModel):
    headline: str
    published_at: datetime
    market: MarketCode = MarketCode.KR
    symbol_code: str | None = None
    source: str = "manual"
    url: str | None = None
    sentiment: Literal["positive", "neutral", "negative"] | None = None
    themes: list[str] | None = None
    raw_payload: dict | None = None


class NewsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market: MarketCode
    symbol_code: str | None
    source: str
    headline: str
    url: str | None
    sentiment: str | None
    published_at: datetime
    themes: list | None
    created_at: datetime


@router.post("/news-events", response_model=NewsRead, status_code=201)
async def create_news(
    payload: NewsCreateRequest, service: NewsContextService = Depends(get_service)
) -> NewsRead:
    news = await service.create_news(
        headline=payload.headline,
        published_at=payload.published_at,
        market=payload.market,
        symbol_code=payload.symbol_code,
        source=payload.source,
        url=payload.url,
        sentiment=payload.sentiment,
        themes=payload.themes,
        raw_payload=payload.raw_payload,
    )
    return NewsRead.model_validate(news)


@router.get("/news-events", response_model=list[NewsRead])
async def list_news(
    market: MarketCode | None = Query(default=None),
    symbol_code: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: NewsContextService = Depends(get_service),
) -> list[NewsRead]:
    items = await service.list_news(
        market=market, symbol_code=symbol_code, limit=limit, offset=offset
    )
    return [NewsRead.model_validate(n) for n in items]


# --- US market -------------------------------------------------------------
class UsSnapshotUpsertRequest(BaseModel):
    session_date: date
    nasdaq_change_pct: Decimal | None = None
    sp500_change_pct: Decimal | None = None
    sox_change_pct: Decimal | None = None
    treasury_10y: Decimal | None = None
    vix: Decimal | None = None
    major_news: list | None = None
    data: dict | None = None


class UsSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_date: date
    nasdaq_change_pct: Decimal | None
    sp500_change_pct: Decimal | None
    sox_change_pct: Decimal | None
    treasury_10y: Decimal | None
    vix: Decimal | None
    major_news: list | None
    data: dict | None
    created_at: datetime


@router.put("/us-market-snapshots", response_model=UsSnapshotRead)
async def upsert_us_snapshot(
    payload: UsSnapshotUpsertRequest, service: NewsContextService = Depends(get_service)
) -> UsSnapshotRead:
    """미국장 스냅샷을 생성하거나 같은 날짜면 갱신한다(멱등)."""
    snapshot = await service.upsert_us_snapshot(
        payload.session_date,
        nasdaq_change_pct=payload.nasdaq_change_pct,
        sp500_change_pct=payload.sp500_change_pct,
        sox_change_pct=payload.sox_change_pct,
        treasury_10y=payload.treasury_10y,
        vix=payload.vix,
        major_news=payload.major_news,
        data=payload.data,
    )
    return UsSnapshotRead.model_validate(snapshot)


@router.get("/us-market-snapshots", response_model=list[UsSnapshotRead])
async def list_us_snapshots(
    limit: int = Query(default=30, ge=1, le=200),
    service: NewsContextService = Depends(get_service),
) -> list[UsSnapshotRead]:
    items = await service.list_us_snapshots(limit=limit)
    return [UsSnapshotRead.model_validate(s) for s in items]


@router.get("/us-market-snapshots/latest", response_model=UsSnapshotRead)
async def get_latest_us_snapshot(
    service: NewsContextService = Depends(get_service),
) -> UsSnapshotRead:
    snapshot = await service.get_latest_us_snapshot()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="no us market snapshot")
    return UsSnapshotRead.model_validate(snapshot)
