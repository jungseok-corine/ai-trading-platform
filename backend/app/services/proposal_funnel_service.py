from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import ProposalStatus
from app.domain.models.scanner_proposal import ScannerRuleProposal
from app.domain.models.strategy_proposal import StrategyProposal
from app.services.proposal_retrospective_service import ProposalRetrospectiveService


class ProposalFunnelService:
    """연구 루프 '제안 퍼널' 집계 (C-3.2).

    AI/수동 제안이 생성 → 승인/거절 → 새 버전(DRAFT) 생성으로 얼마나 흘러가는지를
    전략·스캐너 양쪽으로 모은다. 끝단의 회고(개선/악화)까지 붙여 "연구 루프가 실제로
    가치를 만들고 있는가"를 한 화면에서 본다.

    read-only 집계 — 주문/외부 호출이 없고 어떤 상태도 바꾸지 않는다. 승인/거절은
    여전히 사람이 별도 API로만 한다(여기선 결과를 세기만 한다).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._retro = ProposalRetrospectiveService(session)

    async def funnel(self, days: int = 30) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        strategy = await self._stage_counts(StrategyProposal, since)
        scanner = await self._stage_counts(ScannerRuleProposal, since)
        combined = {
            k: strategy[k] + scanner[k]
            for k in ("generated", "pending", "approved", "rejected", "versions_created")
        }
        combined["approval_rate"] = _rate(combined["approved"], combined["rejected"])
        retrospective = await self._retro.summary()
        return {
            "days": days,
            "strategy": strategy,
            "scanner": scanner,
            "combined": combined,
            "retrospective": retrospective,
        }

    async def _stage_counts(self, model, since: datetime) -> dict:
        rows = (
            await self._session.execute(
                select(model.status, model.created_version_id, func.count(model.id))
                .where(model.created_at >= since)
                .group_by(model.status, model.created_version_id)
            )
        ).all()
        generated = pending = approved = rejected = versions_created = 0
        for status, created_version_id, count in rows:
            generated += count
            if status == ProposalStatus.PENDING:
                pending += count
            elif status == ProposalStatus.APPROVED:
                approved += count
                if created_version_id is not None:
                    versions_created += count
            elif status == ProposalStatus.REJECTED:
                rejected += count
        return {
            "generated": generated,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "versions_created": versions_created,
            "approval_rate": _rate(approved, rejected),
        }


def _rate(approved: int, rejected: int) -> float | None:
    """승인률 = 승인 / (승인+거절). 검토된 게 없으면 None(판단 보류)."""
    reviewed = approved + rejected
    if reviewed == 0:
        return None
    return round(approved / reviewed, 3)
