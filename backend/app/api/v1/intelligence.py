"""Market Intelligence 수집, 후보 발굴, 스캐너 룰 개선 제안 API.

POST /intelligence/ingest                         — 수동 트리거로 전체(또는 선택) 소스 수집 실행. (C-2.22)
POST /intelligence/discover                       — 최근 이벤트에서 관심 후보 종목 발굴. (C-2.24)
GET  /intelligence/candidates                     — 발굴된 후보 목록 조회.
GET  /intelligence/candidates/{id}                — 후보 단건 조회.
POST /intelligence/scanner-proposals/generate     — Intelligence 기반 스캐너 룰 개선 제안 생성. (C-2.25)
POST /intelligence/strategy-proposals/generate    — heuristic 전략 배정 제안 생성. (C-2.26)
GET  /intelligence/strategy-proposals             — 전략 배정 제안 목록 조회. (C-2.26)
GET  /intelligence/strategy-proposals/{id}        — 전략 배정 제안 단건 조회. (C-2.26)
POST /intelligence/strategy-proposals/{id}/approve — 제안 승인 (candidate → PROMOTED). (C-2.26)
POST /intelligence/strategy-proposals/{id}/reject  — 제안 거절. (C-2.26)

모두 read-only 수집·발굴이며 주문·전략 배정과 무관하다.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import (
    IntelligenceCandidateStatus,
    IntelligenceStrategyProposalStatus,
    MarketCode,
)
from app.domain.repositories.intelligence_candidate import IntelligenceCandidateRepository
from app.domain.repositories.intelligence_strategy_proposal import (
    IntelligenceStrategyProposalRepository,
)
from app.services.intelligence_candidate_discovery_service import (
    IntelligenceCandidateDiscoveryService,
)
from app.services.intelligence_ingest_service import IngestSummary, IntelligenceIngestionService
from app.services.intelligence_scanner_proposal_generator import (
    IntelligenceScannerProposalGenerator,
    ProposalGenerationSummary,
)
from app.services.intelligence_strategy_assignment_generator import (
    AssignmentGenerationSummary,
    IntelligenceStrategyAssignmentGenerator,
)

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


# ── Scanner Proposal Generation (C-2.25) ─────────────────────────────────────

class ScannerProposalGenerateRequest(BaseModel):
    candidate_limit: int = 20


class ProposalGenerationSummaryRead(BaseModel):
    candidates_analyzed: int
    scanner_rules_considered: int
    proposals_created: int
    skipped_existing_pending: int
    skipped_invalid: int
    errors: list[str]


@router.post(
    "/scanner-proposals/generate",
    response_model=ProposalGenerationSummaryRead,
    status_code=201,
)
async def generate_scanner_proposals(
    payload: ScannerProposalGenerateRequest,
    session: AsyncSession = Depends(get_db),
) -> ProposalGenerationSummaryRead:
    """Intelligence 후보 패턴을 LLM으로 분석해 기존 스캐너 룰 개선 제안을 생성한다.

    - 새 ScannerRule 생성 없음
    - 생성된 제안은 항상 pending (자동 승인 없음)
    - 승인 시 기존 /scanner-proposals/{id}/approve 흐름으로 DRAFT 버전 생성
    - 외부 네트워크 호출 없음 (DB에 있는 데이터만 사용)
    """
    generator = IntelligenceScannerProposalGenerator(session)
    summary: ProposalGenerationSummary = await generator.generate(
        candidate_limit=payload.candidate_limit,
    )
    return ProposalGenerationSummaryRead(**summary.to_dict())


# ── Strategy Assignment Proposals (C-2.26) ────────────────────────────────────

class StrategyProposalGenerateRequest(BaseModel):
    candidate_limit: int = 50


class AssignmentGenerationSummaryRead(BaseModel):
    candidates_analyzed: int
    proposals_created: int
    skipped_existing: int
    skipped_invalid: int
    errors: list[str]


class IntelligenceStrategyProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    intelligence_candidate_id: int
    symbol_code: str
    market: MarketCode
    suggested_strategy_type: str
    suggested_parameters: dict | None
    rationale: str | None
    confidence_score: float | None
    score_components: dict | None
    source: str
    status: IntelligenceStrategyProposalStatus
    reviewed_at: datetime | None
    reviewer_note: str | None
    dedup_hash: str
    created_at: datetime
    updated_at: datetime


class ProposalReviewRequest(BaseModel):
    reviewer_note: str | None = None


@router.post(
    "/strategy-proposals/generate",
    response_model=AssignmentGenerationSummaryRead,
    status_code=201,
)
async def generate_strategy_proposals(
    payload: StrategyProposalGenerateRequest,
    session: AsyncSession = Depends(get_db),
) -> AssignmentGenerationSummaryRead:
    """PENDING IntelligenceCandidate에서 heuristic 기반 전략 배정 제안을 생성한다.

    - LLM 호출 없음. heuristic 키워드 매칭만 사용.
    - 생성된 제안은 항상 PENDING (자동 승인 없음)
    - StrategyVersion/StrategyAssignmentLog 생성 없음
    - auto_trade_enabled True 없음
    """
    generator = IntelligenceStrategyAssignmentGenerator(session)
    summary: AssignmentGenerationSummary = await generator.generate(
        candidate_limit=payload.candidate_limit,
    )
    return AssignmentGenerationSummaryRead(**summary.to_dict())


@router.get(
    "/strategy-proposals",
    response_model=list[IntelligenceStrategyProposalRead],
)
async def list_strategy_proposals(
    status: IntelligenceStrategyProposalStatus | None = Query(default=None),
    symbol_code: str | None = Query(default=None),
    market: MarketCode | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> list[IntelligenceStrategyProposalRead]:
    """전략 배정 제안 목록 조회 (최신순)."""
    repo = IntelligenceStrategyProposalRepository(session)
    proposals = await repo.list_recent(
        status=status,
        symbol_code=symbol_code,
        market=market,
        limit=limit,
        offset=offset,
    )
    return [IntelligenceStrategyProposalRead.model_validate(p) for p in proposals]


@router.get(
    "/strategy-proposals/{proposal_id}",
    response_model=IntelligenceStrategyProposalRead,
)
async def get_strategy_proposal(
    proposal_id: int,
    session: AsyncSession = Depends(get_db),
) -> IntelligenceStrategyProposalRead:
    repo = IntelligenceStrategyProposalRepository(session)
    proposal = await repo.get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="strategy proposal not found")
    return IntelligenceStrategyProposalRead.model_validate(proposal)


@router.post(
    "/strategy-proposals/{proposal_id}/approve",
    response_model=IntelligenceStrategyProposalRead,
)
async def approve_strategy_proposal(
    proposal_id: int,
    payload: ProposalReviewRequest,
    session: AsyncSession = Depends(get_db),
) -> IntelligenceStrategyProposalRead:
    """제안을 승인한다.

    - proposal.status → APPROVED
    - IntelligenceCandidate.status → PROMOTED
    - StrategyVersion 생성 없음
    - StrategyAssignmentLog 생성 없음
    - auto_trade_enabled True 없음
    """
    proposal_repo = IntelligenceStrategyProposalRepository(session)
    proposal = await proposal_repo.get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="strategy proposal not found")
    if proposal.status != IntelligenceStrategyProposalStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"proposal is already {proposal.status.value}, cannot approve",
        )

    candidate_repo = IntelligenceCandidateRepository(session)
    candidate = await candidate_repo.get(proposal.intelligence_candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="intelligence candidate not found")

    await proposal_repo.approve(proposal, reviewer_note=payload.reviewer_note)
    await candidate_repo.update_status(candidate, IntelligenceCandidateStatus.PROMOTED)
    await session.commit()

    return IntelligenceStrategyProposalRead.model_validate(proposal)


@router.post(
    "/strategy-proposals/{proposal_id}/reject",
    response_model=IntelligenceStrategyProposalRead,
)
async def reject_strategy_proposal(
    proposal_id: int,
    payload: ProposalReviewRequest,
    session: AsyncSession = Depends(get_db),
) -> IntelligenceStrategyProposalRead:
    """제안을 거절한다.

    - proposal.status → REJECTED
    - IntelligenceCandidate.status 변경 없음 (PROMOTED 금지)
    - reviewer_note 저장 가능
    """
    proposal_repo = IntelligenceStrategyProposalRepository(session)
    proposal = await proposal_repo.get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="strategy proposal not found")
    if proposal.status != IntelligenceStrategyProposalStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"proposal is already {proposal.status.value}, cannot reject",
        )

    await proposal_repo.reject(proposal, reviewer_note=payload.reviewer_note)
    await session.commit()

    return IntelligenceStrategyProposalRead.model_validate(proposal)
