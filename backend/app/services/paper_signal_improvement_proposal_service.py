"""Paper Signal AI 분석 리포트 → PENDING 전략 개선 제안(초안) 생성 (M1).

흐름:
  AiAnalysisRun(target_type=paper_signal_session, status=succeeded)
  → AiModelResponse 리포트 본문
  → (구조화 JSON이면) AnalysisProposalService로 검증된 제안, 아니면 보수적 무변경 제안
  → PENDING StrategyProposal (사람 검토 대기)

**하드 경계:** PENDING 제안만 만든다. 승인/머티리얼라이즈/버전 생성/실험/세션/주문 변경 없음.
proposal_service.approve를 호출하지 않는다. 직접 매수/매도 추천을 하지 않는다.
추적: StrategyProposal.ai_analysis_run_id → AiAnalysisRun.target_id(=세션 id). 새 컬럼/마이그레이션 없음.
"""
from __future__ import annotations

from app.domain.models.enums import AnalysisRunStatus, AnalysisTargetType
from app.domain.models.strategy_proposal import StrategyProposal
from app.domain.repositories.ai_analysis import AiAnalysisRunRepository
from app.domain.repositories.strategy import StrategyVersionRepository
from app.domain.repositories.strategy_proposal import StrategyProposalRepository
from app.services.analysis_proposal_service import AnalysisProposalService
from app.services.proposal_service import InvalidProposalError, ProposalService

# 보수적 제안 rationale에 보고서 본문을 담는 상한(거대한 row 방지).
_REPORT_EXCERPT_LIMIT = 2000
_INSUFFICIENT_EVIDENCE = "insufficient evidence — no parameter change recommended"
_SOURCE = "paper_signal_analysis"


class ConfirmationRequiredError(Exception):
    """confirmed=true / confirmed_by 없이 요청할 때."""


class RunNotFoundError(Exception):
    """ai_analysis_run id가 없을 때."""


class RunNotSucceededError(Exception):
    """run.status가 succeeded가 아닐 때."""


class InvalidTargetTypeError(Exception):
    """run.target_type이 paper_signal_session이 아닐 때."""


class NoReportContentError(Exception):
    """본문이 있는 AiModelResponse가 없을 때."""


class MissingVersionLinkError(Exception):
    """run에 strategy_version 연결이 없거나 버전을 찾을 수 없을 때."""


class DuplicatePendingProposalError(Exception):
    """같은 run에 대한 PENDING 제안이 이미 있을 때."""


class PaperSignalImprovementProposalService:
    def __init__(self, session) -> None:
        self._session = session
        self._run_repo = AiAnalysisRunRepository(session)
        self._version_repo = StrategyVersionRepository(session)
        self._proposal_repo = StrategyProposalRepository(session)
        self._analysis_proposal_service = AnalysisProposalService(session)
        self._proposal_service = ProposalService(session)

    async def create_from_analysis_run(
        self,
        run_id: int,
        confirmed: bool,
        confirmed_by: str | None,
        proposal_kind: str = "strategy",
    ) -> StrategyProposal:
        if not confirmed:
            raise ConfirmationRequiredError("confirmed must be true")
        if not confirmed_by:
            raise ConfirmationRequiredError("confirmed_by is required")

        run = await self._run_repo.get_with_responses(run_id)
        if run is None:
            raise RunNotFoundError(run_id)
        if run.status != AnalysisRunStatus.SUCCEEDED:
            raise RunNotSucceededError(f"run {run_id} status is {run.status.value}, not succeeded")
        if run.target_type != AnalysisTargetType.PAPER_SIGNAL_SESSION:
            raise InvalidTargetTypeError(
                f"run {run_id} target_type is {run.target_type.value}, not paper_signal_session"
            )

        content = next((r.content for r in run.responses if r.content), None)
        if not content:
            raise NoReportContentError(f"run {run_id} has no model response content")

        version_id = run.strategy_version_id
        if version_id is None:
            raise MissingVersionLinkError(f"run {run_id} has no strategy_version_id")
        version = await self._version_repo.get(version_id)
        if version is None:
            raise MissingVersionLinkError(f"strategy_version {version_id} not found")
        strategy_id = version.strategy_id

        # 중복 PENDING 방지.
        existing = await self._proposal_repo.find_pending_for_analysis_run(run_id)
        if existing is not None:
            raise DuplicatePendingProposalError(
                f"a pending proposal already exists for run {run_id} (#{existing.id})"
            )

        session_id = run.target_id  # 추적용(= paper_signal_session.id)

        # 1) 구조화 경로: 리포트가 검증 가능한 JSON 가설이면 검증된 제안을 만든다(없으면 None).
        structured = await self._analysis_proposal_service.create_from_text(
            strategy_id=strategy_id,
            version_id=version_id,
            analysis_text=content,
            ai_analysis_run_id=run_id,
        )
        if structured is not None:
            return structured

        # 2) 보수적 폴백: 명시·검증된 파라미터 변경이 없으면 '무변경' 검토용 초안을 만든다.
        # suggested_parameters는 현재 버전 파라미터(=무변경). 파라미터를 지어내지 않는다.
        no_change_params = dict(version.parameters or {})
        excerpt = content[:_REPORT_EXCERPT_LIMIT]
        rationale = (
            f"Paper signal 세션 #{session_id} AI 분석 리포트 기반 검토용 초안. "
            f"명시적·검증된 파라미터 변경이 없어 변경을 제안하지 않음 ({_INSUFFICIENT_EVIDENCE}).\n\n"
            f"[리포트 발췌]\n{excerpt}"
        )
        try:
            return await self._proposal_service.create_proposal(
                strategy_id=strategy_id,
                suggested_parameters=no_change_params,
                title=f"Paper signal 분석 개선 제안 초안 (세션 #{session_id}, run #{run_id})",
                summary="AI 분석 리포트 기반 검토용 초안 — 자동 반영 아님 (PENDING)",
                rationale=rationale,
                expected_effect=None,
                risk_notes=(
                    "검토용 초안. 승인 전까지 아무 것도 적용되지 않음. "
                    "소표본/단기 신호 한계 주의. 직접 매매 권고 아님."
                ),
                base_version_id=version_id,
                source=_SOURCE,
                ai_analysis_run_id=run_id,
            )
        except InvalidProposalError as exc:
            # 현재 버전 파라미터가 검증을 통과하지 못하는 비정상 케이스 → 링크 누락으로 처리.
            raise MissingVersionLinkError(str(exc)) from exc

    async def list_for_analysis_run(self, run_id: int, limit: int = 50) -> list[StrategyProposal]:
        return await self._proposal_repo.list_by_analysis_run(run_id, limit=limit)


__all__ = [
    "PaperSignalImprovementProposalService",
    "ConfirmationRequiredError",
    "RunNotFoundError",
    "RunNotSucceededError",
    "InvalidTargetTypeError",
    "NoReportContentError",
    "MissingVersionLinkError",
    "DuplicatePendingProposalError",
]
