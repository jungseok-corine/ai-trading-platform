"""Market Intelligence 수집 및 후보 발굴 API (C-2.22 / C-2.24).

POST /intelligence/ingest    — 수동 트리거로 전체(또는 선택) 소스 수집 실행.
POST /intelligence/discover  — 최근 이벤트에서 관심 후보 종목 발굴.
GET  /intelligence/candidates         — 발굴된 후보 목록 조회.
GET  /intelligence/candidates/{id}    — 후보 단건 조회.

모두 read-only 수집·발굴이며 주문·전략 배정과 무관하다.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import IntelligenceCandidateStatus, MarketCode
from app.domain.repositories.intelligence_candidate import IntelligenceCandidateRepository
from app.services.intelligence_candidate_discovery_service import (
    IntelligenceCandidateDiscoveryService,
)
from app.services.intelligence_ingest_service import IngestSummary, IntelligenceIngestionService

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


# ── Ingest (C-2.22) ───────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    source_keys: list[str] | None = None


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


# ── Discovery (C-2.24) ────────────────────────────────────────────────────────

class DiscoverRequest(BaseModel):
    lookback_hours: int = 24
    event_limit: int = 100


class DiscoverySummaryRead(BaseModel):
    events_checked: int
    candidates_created: int
    skipped_duplicate_count: int
    skipped_no_symbol_count: int
    errors: list[str]


class IntelligenceCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    intelligence_event_id: int | None
    symbol_code: str
    market: MarketCode
    score: int
    why_text: str | None
    status: IntelligenceCandidateStatus
    source_type: str | None
    matched_themes: list | None
    score_components: dict | None
    dedup_hash: str
    created_at: datetime
    updated_at: datetime


@router.post("/discover", response_model=DiscoverySummaryRead, status_code=201)
async def trigger_discovery(
    payload: DiscoverRequest,
    session: AsyncSession = Depends(get_db),
) -> DiscoverySummaryRead:
    """최근 IntelligenceEvent에서 관심 후보 종목을 발굴한다.

    symbol_code가 있는 이벤트를 후보화하며 dedup_hash로 중복을 방지한다.
    LLM 호출 없음. 실주문 없음.
    """
    svc = IntelligenceCandidateDiscoveryService(session)
    summary = await svc.discover(
        lookback_hours=payload.lookback_hours,
        event_limit=payload.event_limit,
    )
    return DiscoverySummaryRead(**summary.to_dict())


@router.get("/candidates", response_model=list[IntelligenceCandidateRead])
async def list_candidates(
    status: IntelligenceCandidateStatus | None = Query(default=None),
    symbol_code: str | None = Query(default=None),
    market: MarketCode | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> list[IntelligenceCandidateRead]:
    """발굴된 IntelligenceCandidate 목록 조회 (최신순)."""
    repo = IntelligenceCandidateRepository(session)
    candidates = await repo.list_recent(
        status=status,
        symbol_code=symbol_code,
        market=market,
        limit=limit,
        offset=offset,
    )
    return [IntelligenceCandidateRead.model_validate(c) for c in candidates]


@router.get("/candidates/{candidate_id}", response_model=IntelligenceCandidateRead)
async def get_candidate(
    candidate_id: int,
    session: AsyncSession = Depends(get_db),
) -> IntelligenceCandidateRead:
    repo = IntelligenceCandidateRepository(session)
    candidate = await repo.get(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="intelligence candidate not found")
    return IntelligenceCandidateRead.model_validate(candidate)
