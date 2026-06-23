"""Market Intelligence 수집 API (C-2.22).

POST /intelligence/ingest — 수동 트리거로 전체(또는 선택) 소스 수집 실행.
read-only 수집이며 주문과 무관하다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.intelligence_ingest_service import IngestSummary, IntelligenceIngestionService

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


class IngestRequest(BaseModel):
    source_keys: list[str] | None = None  # None이면 전체 enabled 소스 실행


class IngestSummaryRead(BaseModel):
    sources_checked: int
    fetched_count: int
    inserted_count: int
    skipped_duplicate_count: int
    error_count: int
    errors: list[dict]


@router.post("/ingest", response_model=IngestSummaryRead)
async def trigger_ingest(
    payload: IngestRequest,
    session: AsyncSession = Depends(get_db),
) -> IngestSummaryRead:
    """Intelligence pipeline 수동 트리거.

    enabled IntelligenceSource를 순회해 fetch → normalize → dedup → 저장한다.
    source_keys를 지정하면 해당 소스만 실행한다.
    """
    svc = IntelligenceIngestionService(session)
    summary: IngestSummary = await svc.ingest(source_keys=payload.source_keys)
    return IngestSummaryRead(**summary.to_dict())
