"""시장/테마 맥락(Market Context) API (C-2.22).

signal/trade에 연결할 시장 맥락 스냅샷과 테마/종목 매핑을 관리한다.
모두 read/write 메타데이터 작업이며 주문과 무관하다.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import MarketCode
from app.services.market_context_service import MarketContextService

router = APIRouter(prefix="/market-context", tags=["market-context"])


def get_service(session: AsyncSession = Depends(get_db)) -> MarketContextService:
    return MarketContextService(session)


# --- schemas ---------------------------------------------------------------
class SnapshotCreateRequest(BaseModel):
    market: MarketCode = MarketCode.KR
    time_bucket: str | None = None
    index_trend: str | None = None
    foreign_flow: str | None = None
    institution_flow: str | None = None
    individual_flow: str | None = None
    news_sentiment: str | None = None
    indices: dict | None = None
    us_previous_session: dict | None = None
    fx: dict | None = None
    data: dict | None = None


class SnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market: MarketCode
    captured_at: datetime
    time_bucket: str | None
    index_trend: str | None
    foreign_flow: str | None
    institution_flow: str | None
    individual_flow: str | None
    news_sentiment: str | None
    indices: dict | None
    us_previous_session: dict | None
    fx: dict | None
    data: dict | None
    created_at: datetime


class ThemeCreateRequest(BaseModel):
    market: MarketCode = MarketCode.KR
    code: str
    name: str


class ThemeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market: MarketCode
    code: str
    name: str
    created_at: datetime


class TagSymbolRequest(BaseModel):
    symbol_code: str
    theme_id: int
    market: MarketCode = MarketCode.KR


# --- snapshots -------------------------------------------------------------
@router.post("/snapshots", response_model=SnapshotRead, status_code=201)
async def create_snapshot(
    payload: SnapshotCreateRequest,
    service: MarketContextService = Depends(get_service),
) -> SnapshotRead:
    snapshot = await service.create_snapshot(**payload.model_dump())
    return SnapshotRead.model_validate(snapshot)


@router.get("/snapshots", response_model=list[SnapshotRead])
async def list_snapshots(
    market: MarketCode | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    service: MarketContextService = Depends(get_service),
) -> list[SnapshotRead]:
    snapshots = await service.list_snapshots(market=market, limit=limit)
    return [SnapshotRead.model_validate(s) for s in snapshots]


# --- themes ----------------------------------------------------------------
@router.post("/themes", response_model=ThemeRead, status_code=201)
async def create_theme(
    payload: ThemeCreateRequest,
    service: MarketContextService = Depends(get_service),
) -> ThemeRead:
    theme = await service.upsert_theme(payload.market, payload.code, payload.name)
    return ThemeRead.model_validate(theme)


@router.get("/themes", response_model=list[ThemeRead])
async def list_themes(
    market: MarketCode | None = Query(default=None),
    service: MarketContextService = Depends(get_service),
) -> list[ThemeRead]:
    themes = await service.list_themes(market=market)
    return [ThemeRead.model_validate(t) for t in themes]


@router.post("/themes/tag-symbol", status_code=200)
async def tag_symbol(
    payload: TagSymbolRequest,
    service: MarketContextService = Depends(get_service),
) -> dict:
    created = await service.tag_symbol(payload.symbol_code, payload.theme_id, payload.market)
    return {"created": created}


@router.get("/symbols/{symbol_code}/themes", response_model=list[ThemeRead])
async def list_symbol_themes(
    symbol_code: str,
    service: MarketContextService = Depends(get_service),
) -> list[ThemeRead]:
    themes = await service.list_themes_for_symbol(symbol_code)
    return [ThemeRead.model_validate(t) for t in themes]
