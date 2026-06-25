"""GET /api/v1/analysis-runs/{run_id} — 단일 분석 run 조회 + 개선 제안 초안(M1)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.strategy_proposals import ProposalRead
from app.db.session import get_db
from app.services.ai_analysis.run_schemas import AnalysisRunRead
from app.services.ai_analysis.run_service import AnalysisRunService
from app.services.paper_signal_improvement_proposal_service import (
    ConfirmationRequiredError,
    DuplicatePendingProposalError,
    InvalidTargetTypeError,
    MissingVersionLinkError,
    NoReportContentError,
    PaperSignalImprovementProposalService,
    RunNotFoundError,
    RunNotSucceededError,
)

router = APIRouter(prefix="/analysis-runs", tags=["analysis-runs"])


def get_run_service(session: AsyncSession = Depends(get_db)) -> AnalysisRunService:
    return AnalysisRunService(session)


def get_improvement_proposal_service(
    session: AsyncSession = Depends(get_db),
) -> PaperSignalImprovementProposalService:
    return PaperSignalImprovementProposalService(session)


@router.get("/{run_id}", response_model=AnalysisRunRead)
async def get_analysis_run(
    run_id: int,
    service: AnalysisRunService = Depends(get_run_service),
) -> AnalysisRunRead:
    """분석 run을 조회한다. responses(모델 응답 목록)를 포함한다."""
    run = await service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="analysis run not found")
    return AnalysisRunRead.model_validate(run)


class ImprovementProposalRequest(BaseModel):
    confirmed: bool = False
    confirmed_by: str | None = None
    proposal_kind: str = "strategy"  # strategy | auto (V1: strategy)


@router.post(
    "/{run_id}/improvement-proposals",
    response_model=ProposalRead,
    status_code=201,
)
async def create_improvement_proposal(
    run_id: int,
    payload: ImprovementProposalRequest,
    service: PaperSignalImprovementProposalService = Depends(get_improvement_proposal_service),
) -> ProposalRead:
    """paper signal 분석 run에서 **PENDING** 개선 제안 초안을 만든다.

    검토용 초안만 생성한다 — 승인/머티리얼라이즈/전략·세션·실험 상태 변경/주문 없음.
    이후 검토(승인/거절)는 기존 AI 전략 제안 화면(ProposalsSection)에서 사람이 한다.
    """
    try:
        proposal = await service.create_from_analysis_run(
            run_id,
            confirmed=payload.confirmed,
            confirmed_by=payload.confirmed_by,
            proposal_kind=payload.proposal_kind,
        )
    except RunNotFoundError as e:
        raise HTTPException(status_code=404, detail="analysis run not found") from e
    except ConfirmationRequiredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RunNotSucceededError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except InvalidTargetTypeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except NoReportContentError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except MissingVersionLinkError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except DuplicatePendingProposalError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return ProposalRead.model_validate(proposal)


@router.get(
    "/{run_id}/improvement-proposals",
    response_model=list[ProposalRead],
)
async def list_improvement_proposals(
    run_id: int,
    service: PaperSignalImprovementProposalService = Depends(get_improvement_proposal_service),
) -> list[ProposalRead]:
    """이 분석 run에서 만들어진 제안 목록(최신순)."""
    proposals = await service.list_for_analysis_run(run_id)
    return [ProposalRead.model_validate(p) for p in proposals]
