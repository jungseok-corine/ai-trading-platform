"""후보 종목 → 전략 배정 제안(PENDING) 생성/조회/검토 서비스 (V1).

제안만 한다. 어떤 실행도 하지 않는다:
- StrategyVersion / StrategyAssignmentLog / Experiment / Trade / Order 생성 없음.
- AssignmentService(확정 배정) 호출 없음.
- 자동매매 토글/실거래 활성 플래그 미변경.
- review()는 status(approved/rejected)만 갱신하며 아무것도 실행하지 않는다.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.candidate_strategy_proposal import CandidateStrategyProposal
from app.domain.repositories.candidate_event import CandidateEventRepository
from app.domain.repositories.candidate_strategy_proposal import (
    CandidateStrategyProposalRepository,
)
from app.trading.strategy.registry import registered_types


class CandidateNotFoundError(Exception):
    """candidate_event_id가 존재하지 않을 때."""


class ProposalNotFoundError(Exception):
    """candidate_strategy_proposal id가 존재하지 않을 때."""


class InvalidStrategyTypeError(Exception):
    """등록되지 않은 strategy_type을 제안했을 때."""


class InvalidReviewStatusError(Exception):
    """review status가 approved/rejected가 아닐 때."""


# 스캐너 매칭 조건 → 검토용 기본 전략 템플릿 제안 (heuristic, read-only 근거).
# body로 strategy_type을 명시하지 않으면 후보의 matched_conditions에서 유추한다.
_CONDITION_GUIDE: dict[str, tuple[str, str]] = {
    "volume_spike": ("volume_confirmed_ma_cross", "거래량 급증 — 거래량 확인형 추세 전략"),
    "price_change_pct": ("momentum_surge", "단기 상승률 — 상승 모멘텀 전략"),
    "turnover_rank": ("breakout_high", "거래대금 상위 — 신고가/돌파형 전략"),
    "investor_flow": ("flow_confirmed_volume_ma_cross", "수급 신호 — 수급 확인형 전략"),
    "time_bucket": ("moving_average_cross", "시간대 조건 — 기본 추세 전략부터 검토"),
}
_FALLBACK = ("moving_average_cross", "특이 신호 없음 — 기본 이동평균 교차 전략부터 검토")

_VALID_REVIEW_STATUSES = {"approved", "rejected"}


def _derive_suggestion(matched_conditions: list | None) -> tuple[str, str]:
    for cond in matched_conditions or []:
        if cond in _CONDITION_GUIDE:
            return _CONDITION_GUIDE[cond]
    return _FALLBACK


class CandidateStrategyProposalService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = CandidateStrategyProposalRepository(session)
        self._candidate_repo = CandidateEventRepository(session)

    async def create(
        self,
        candidate_event_id: int,
        suggested_strategy_type: str | None = None,
        rationale: str | None = None,
        confidence: float | None = None,
        suggested_parameters: dict | None = None,
        source: str = "manual",
    ) -> CandidateStrategyProposal:
        """후보에 대한 PENDING 전략 제안을 만든다. 같은 후보+전략의 PENDING 중복은 기존 것을 반환.

        실행/배정/버전 생성을 하지 않는다. 항상 status="pending"으로 저장한다.
        """
        candidate = await self._candidate_repo.get(candidate_event_id)
        if candidate is None:
            raise CandidateNotFoundError(candidate_event_id)

        # body 미지정 시 후보 facts에서 안전한 기본값 유추.
        derived_type, derived_reason = _derive_suggestion(candidate.matched_conditions)
        strategy_type = suggested_strategy_type or derived_type
        if strategy_type not in registered_types():
            raise InvalidStrategyTypeError(
                f"unknown strategy_type {strategy_type!r}. "
                f"registered: {sorted(registered_types())}"
            )
        if rationale is None:
            rationale = derived_reason
        if confidence is None and candidate.score:
            confidence = round(candidate.score / 100.0, 4)

        # 안전: 실행 토글이 제안 파라미터에 섞여 들어오지 않도록 제거.
        params = dict(suggested_parameters) if suggested_parameters else None
        if params:
            params.pop("auto_trade_enabled", None)

        existing = await self._repo.find_pending_duplicate(candidate_event_id, strategy_type)
        if existing is not None:
            return existing

        proposal = await self._repo.create(
            candidate_event_id=candidate.id,
            symbol_code=candidate.symbol_code,
            suggested_strategy_type=strategy_type,
            rationale=rationale,
            confidence=confidence,
            suggested_parameters=params,
            status="pending",
            source=source,
        )
        await self._session.commit()
        return proposal

    async def list_for_candidate(
        self, candidate_event_id: int
    ) -> list[CandidateStrategyProposal]:
        return await self._repo.list_for_candidate(candidate_event_id)

    async def list_recent(
        self, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[CandidateStrategyProposal]:
        return await self._repo.list_recent(status=status, limit=limit, offset=offset)

    async def review(
        self,
        proposal_id: int,
        status: str,
        reviewed_by: str | None = None,
        review_note: str | None = None,
    ) -> CandidateStrategyProposal:
        """제안의 status만 approved/rejected로 갱신한다. 아무것도 실행하지 않는다."""
        if status not in _VALID_REVIEW_STATUSES:
            raise InvalidReviewStatusError(status)
        proposal = await self._repo.get(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(proposal_id)
        proposal = await self._repo.update(
            proposal,
            status=status,
            reviewed_by=reviewed_by,
            review_note=review_note,
            reviewed_at=datetime.now(timezone.utc),
        )
        await self._session.commit()
        return proposal
