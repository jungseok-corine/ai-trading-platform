from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import ProposalStatus, StrategyVersionStatus
from app.domain.models.strategy import StrategyVersion
from app.domain.models.strategy_proposal import StrategyProposal
from app.domain.repositories.strategy import (
    StrategyRepository,
    StrategyVersionRepository,
)
from app.domain.repositories.strategy_proposal import StrategyProposalRepository
from app.services.strategy_service import StrategyNotFoundError, StrategyService
from app.trading.strategy.registry import registered_types

KST = ZoneInfo("Asia/Seoul")


class ProposalNotFoundError(Exception):
    """proposal_id가 존재하지 않을 때 발생."""


class InvalidProposalError(Exception):
    """제안 내용이 유효하지 않을 때 발생(예: 미등록 strategy_type)."""


class ProposalNotPendingError(Exception):
    """이미 검토된(approved/rejected) 제안을 다시 검토하려 할 때 발생."""


@dataclass
class ParamDiff:
    key: str
    before: Any
    after: Any


def compute_diff(before: dict, after: dict) -> list[ParamDiff]:
    """두 파라미터 dict의 변경점을 반환한다(추가/삭제/변경된 키만)."""
    diffs: list[ParamDiff] = []
    for key in sorted(set(before) | set(after)):
        b = before.get(key)
        a = after.get(key)
        if b != a:
            diffs.append(ParamDiff(key=key, before=b, after=a))
    return diffs


class ProposalService:
    """전략 개선 제안의 저장·조회·승인/거절을 담당한다 (C-2.27).

    승인 시에만 새 strategy_version(DRAFT)을 생성한다. AI는 직접 전략을 활성화하거나
    auto_trade를 켤 수 없으며, 승인으로 생성되는 버전은 항상 auto_trade_enabled=False다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._proposal_repo = StrategyProposalRepository(session)
        self._strategy_repo = StrategyRepository(session)
        self._version_repo = StrategyVersionRepository(session)
        self._strategy_service = StrategyService(session)

    async def create_proposal(
        self,
        strategy_id: int,
        suggested_parameters: dict,
        title: str,
        summary: str | None = None,
        rationale: str | None = None,
        expected_effect: str | None = None,
        risk_notes: str | None = None,
        base_version_id: int | None = None,
        source: str = "ai",
        ai_analysis_run_id: int | None = None,
    ) -> StrategyProposal:
        strategy = await self._strategy_repo.get(strategy_id)
        if strategy is None:
            raise StrategyNotFoundError(strategy_id)

        strategy_type = suggested_parameters.get("strategy_type")
        if strategy_type not in registered_types():
            raise InvalidProposalError(
                f"suggested_parameters.strategy_type {strategy_type!r} is not registered. "
                f"registered: {sorted(registered_types())}"
            )

        if base_version_id is not None:
            base = await self._version_repo.get(base_version_id)
            if base is None or base.strategy_id != strategy_id:
                raise InvalidProposalError(
                    f"base_version_id {base_version_id} does not belong to strategy {strategy_id}"
                )

        proposal = await self._proposal_repo.create(
            strategy_id=strategy_id,
            base_version_id=base_version_id,
            ai_analysis_run_id=ai_analysis_run_id,
            title=title,
            summary=summary,
            rationale=rationale,
            expected_effect=expected_effect,
            risk_notes=risk_notes,
            suggested_parameters=suggested_parameters,
            source=source,
        )
        await self._session.commit()
        return proposal

    async def list_proposals(
        self,
        strategy_id: int | None = None,
        status: ProposalStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StrategyProposal]:
        return await self._proposal_repo.list_filtered(
            strategy_id=strategy_id, status=status, limit=limit, offset=offset
        )

    async def get_proposal(self, proposal_id: int) -> StrategyProposal | None:
        return await self._proposal_repo.get(proposal_id)

    async def diff_for(self, proposal: StrategyProposal) -> list[ParamDiff]:
        before: dict = {}
        if proposal.base_version_id is not None:
            base = await self._version_repo.get(proposal.base_version_id)
            if base is not None:
                before = base.parameters or {}
        return compute_diff(before, proposal.suggested_parameters or {})

    async def approve(
        self,
        proposal_id: int,
        reviewed_by: str | None = None,
        review_note: str | None = None,
    ) -> tuple[StrategyProposal, StrategyVersion]:
        """제안을 승인하고, suggested_parameters로 새 DRAFT 버전을 생성한다.

        안전장치: 생성되는 버전은 항상 auto_trade_enabled=False, status=DRAFT다.
        이미 검토된 제안은 ProposalNotPendingError를 발생시킨다.
        """
        proposal = await self._proposal_repo.get(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(proposal_id)
        if proposal.status != ProposalStatus.PENDING:
            raise ProposalNotPendingError(proposal_id)

        # 안전장치: AI 제안이 자동매매를 켜지 못하도록 강제로 비활성화한다.
        params = dict(proposal.suggested_parameters or {})
        params["auto_trade_enabled"] = False

        version = await self._strategy_service.create_version(
            proposal.strategy_id,
            parameters=params,
            change_description=f"AI 제안 #{proposal.id} 승인: {proposal.title}",
            status=StrategyVersionStatus.DRAFT,
        )

        proposal.status = ProposalStatus.APPROVED
        proposal.created_version_id = version.id
        proposal.reviewed_by = reviewed_by
        proposal.review_note = review_note
        proposal.reviewed_at = datetime.now(KST)
        await self._session.commit()
        return proposal, version

    async def reject(
        self,
        proposal_id: int,
        reviewed_by: str | None = None,
        review_note: str | None = None,
    ) -> StrategyProposal:
        proposal = await self._proposal_repo.get(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(proposal_id)
        if proposal.status != ProposalStatus.PENDING:
            raise ProposalNotPendingError(proposal_id)

        proposal.status = ProposalStatus.REJECTED
        proposal.reviewed_by = reviewed_by
        proposal.review_note = review_note
        proposal.reviewed_at = datetime.now(KST)
        await self._session.commit()
        return proposal
