from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_cost_service import AiCostService
from app.services.proposal_funnel_service import ProposalFunnelService
from app.services.research_status_service import ResearchStatusService
from app.services.safety_status_service import SafetyStatusService


class OperationsOverviewService:
    """운영 종합 관제 (C-3.5).

    안전 점검(C-3.3) · 연구 루프 상태(C-2.43) · 제안 퍼널(C-3.2) · AI 비용(C-3.1)의
    핵심 헤드라인만 모아 한 화면 랜딩으로 만든다. 세부는 각 전용 탭에서 본다.
    read-only 합본 — 기존 read-only 서비스들을 조합만 하며 아무것도 바꾸지 않는다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._safety = SafetyStatusService(session)
        self._research = ResearchStatusService(session)
        self._funnel = ProposalFunnelService(session)
        self._cost = AiCostService(session)

    async def overview(self, days: int = 30) -> dict:
        safety = await self._safety.status()
        research = await self._research.status()
        research_d = research.to_dict()
        funnel = await self._funnel.funnel(days=days)
        cost = await self._cost.summary(days=days)

        return {
            "days": days,
            "safety": {
                "invariants_ok": safety["invariants_ok"],
                "warnings": safety["warnings"],
            },
            "research": {
                "pending_total": research_d["pending"]["total"],
                "active_strategy_versions": research_d["active"]["strategy_versions"],
                "active_scanner_versions": research_d["active"]["scanner_versions"],
                "disclosure_alerts": research_d["disclosure_alerts"],
                "macro_regime": research_d["macro"].get("regime"),
            },
            "funnel": {
                "generated": funnel["combined"]["generated"],
                "approved": funnel["combined"]["approved"],
                "versions_created": funnel["combined"]["versions_created"],
                "approval_rate": funnel["combined"]["approval_rate"],
            },
            "retrospective": funnel["retrospective"],
            "cost": {
                "responses": cost["total"]["responses"],
                "total_tokens": cost["total"]["total_tokens"],
                "est_cost_usd": cost["total"]["est_cost_usd"],
            },
        }
