from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import ProposalStatus, ScannerRuleStatus
from app.domain.models.scanner import ScannerRuleVersion
from app.domain.models.scanner_proposal import ScannerRuleProposal
from app.domain.repositories.scanner import (
    ScannerRuleRepository,
    ScannerRuleVersionRepository,
)
from app.domain.repositories.scanner_proposal import ScannerRuleProposalRepository
from app.services.scanner_service import (
    ScannerRuleNotFoundError,
    ScannerRuleVersionNotFoundError,
    ScannerService,
)
from app.trading.scanner.conditions import validate_conditions

KST = ZoneInfo("Asia/Seoul")


class ScannerProposalNotFoundError(Exception):
    """proposal_id가 존재하지 않을 때 발생."""


class ScannerProposalNotPendingError(Exception):
    """이미 검토된(approved/rejected) 제안을 다시 검토하려 할 때 발생."""


@dataclass
class ConditionDiff:
    type: str
    before: Any
    after: Any


def _index_by_type(conditions: list[dict]) -> dict[str, Any]:
    """조건 리스트를 type → params 맵으로 만든다(같은 type이 여러 개면 마지막이 우선)."""
    out: dict[str, Any] = {}
    for c in conditions or []:
        out[c.get("type")] = c.get("params", {})
    return out


def compute_condition_diff(before: list[dict], after: list[dict]) -> list[ConditionDiff]:
    """두 조건 리스트의 변경점을 type 기준으로 반환한다(추가/삭제/변경된 type만)."""
    b = _index_by_type(before)
    a = _index_by_type(after)
    diffs: list[ConditionDiff] = []
    for key in sorted(set(b) | set(a)):
        bp = b.get(key)
        ap = a.get(key)
        if bp != ap:
            diffs.append(ConditionDiff(type=key, before=bp, after=ap))
    return diffs


class ScannerProposalService:
    """스캐너 룰 개선 제안의 저장·조회·승인/거절을 담당한다 (C-2.39).

    승인 시에만 새 scanner_rule_version(DRAFT)을 생성한다. AI는 직접 룰을 활성화하거나
    실거래를 켤 수 없으며, 승인으로 생성되는 버전은 항상 status=DRAFT다(문서 2.3 / 13.3).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._proposal_repo = ScannerRuleProposalRepository(session)
        self._rule_repo = ScannerRuleRepository(session)
        self._version_repo = ScannerRuleVersionRepository(session)
        self._scanner_service = ScannerService(session)

    async def create_proposal(
        self,
        scanner_rule_id: int,
        suggested_conditions: list[dict],
        title: str,
        summary: str | None = None,
        rationale: str | None = None,
        expected_effect: str | None = None,
        risk_notes: str | None = None,
        base_version_id: int | None = None,
        source: str = "ai",
    ) -> ScannerRuleProposal:
        rule = await self._rule_repo.get(scanner_rule_id)
        if rule is None:
            raise ScannerRuleNotFoundError(scanner_rule_id)

        # 제안 조건도 저장 전에 검증한다(승인 시 그대로 새 버전이 되므로).
        validated = validate_conditions(suggested_conditions)
        normalized = [c.model_dump(mode="json") for c in validated]

        if base_version_id is not None:
            base = await self._version_repo.get(base_version_id)
            if base is None or base.scanner_rule_id != scanner_rule_id:
                raise ScannerRuleVersionNotFoundError(base_version_id)

        proposal = await self._proposal_repo.create(
            scanner_rule_id=scanner_rule_id,
            base_version_id=base_version_id,
            title=title,
            summary=summary,
            rationale=rationale,
            expected_effect=expected_effect,
            risk_notes=risk_notes,
            suggested_conditions=normalized,
            source=source,
        )
        await self._session.commit()
        return proposal

    async def list_proposals(
        self,
        scanner_rule_id: int | None = None,
        status: ProposalStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ScannerRuleProposal]:
        return await self._proposal_repo.list_filtered(
            scanner_rule_id=scanner_rule_id, status=status, limit=limit, offset=offset
        )

    async def get_proposal(self, proposal_id: int) -> ScannerRuleProposal | None:
        return await self._proposal_repo.get(proposal_id)

    async def diff_for(self, proposal: ScannerRuleProposal) -> list[ConditionDiff]:
        before: list[dict] = []
        if proposal.base_version_id is not None:
            base = await self._version_repo.get(proposal.base_version_id)
            if base is not None:
                before = base.conditions or []
        return compute_condition_diff(before, proposal.suggested_conditions or [])

    async def approve(
        self,
        proposal_id: int,
        reviewed_by: str | None = None,
        review_note: str | None = None,
    ) -> tuple[ScannerRuleProposal, ScannerRuleVersion]:
        """제안을 승인하고, suggested_conditions로 새 DRAFT 룰 버전을 생성한다.

        안전장치: 생성되는 버전은 항상 status=DRAFT다(자동 활성화 금지).
        이미 검토된 제안은 ScannerProposalNotPendingError를 발생시킨다.
        """
        proposal = await self._proposal_repo.get(proposal_id)
        if proposal is None:
            raise ScannerProposalNotFoundError(proposal_id)
        if proposal.status != ProposalStatus.PENDING:
            raise ScannerProposalNotPendingError(proposal_id)

        version = await self._scanner_service.create_version(
            proposal.scanner_rule_id,
            conditions=proposal.suggested_conditions or [],
            change_description=f"AI 제안 #{proposal.id} 승인: {proposal.title}",
            status=ScannerRuleStatus.DRAFT,
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
    ) -> ScannerRuleProposal:
        proposal = await self._proposal_repo.get(proposal_id)
        if proposal is None:
            raise ScannerProposalNotFoundError(proposal_id)
        if proposal.status != ProposalStatus.PENDING:
            raise ScannerProposalNotPendingError(proposal_id)

        proposal.status = ProposalStatus.REJECTED
        proposal.reviewed_by = reviewed_by
        proposal.review_note = review_note
        proposal.reviewed_at = datetime.now(KST)
        await self._session.commit()
        return proposal

    async def bulk_review(
        self,
        proposal_ids: list[int],
        action: str,
        reviewed_by: str | None = None,
        review_note: str | None = None,
    ) -> dict:
        """여러 제안을 한 번에 승인/거절한다. 개별 실패는 격리해 결과에 모은다.

        action: "approve" | "reject". 승인 시 각 제안마다 새 DRAFT 룰 버전이 생성된다.
        """
        if action not in ("approve", "reject"):
            raise ValueError(f"invalid action: {action!r} (expected approve/reject)")
        succeeded: list[int] = []
        failed: list[dict] = []
        for pid in proposal_ids:
            try:
                if action == "approve":
                    await self.approve(pid, reviewed_by=reviewed_by, review_note=review_note)
                else:
                    await self.reject(pid, reviewed_by=reviewed_by, review_note=review_note)
                succeeded.append(pid)
            except ScannerProposalNotFoundError:
                failed.append({"id": pid, "reason": "not found"})
            except ScannerProposalNotPendingError:
                failed.append({"id": pid, "reason": "already reviewed"})
        return {"action": action, "succeeded": succeeded, "failed": failed}
