from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_cost_service import AiCostService
from app.services.promotion_readiness_service import PromotionReadinessService
from app.services.proposal_funnel_service import ProposalFunnelService
from app.services.research_status_service import ResearchStatusService
from app.services.risk_event_summary_service import RiskEventSummaryService
from app.services.safety_status_service import SafetyStatusService
from app.services.trade_activity_service import TradeActivityService


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
        self._trades = TradeActivityService(session)
        self._risk = RiskEventSummaryService(session)
        self._readiness = PromotionReadinessService(session)

    async def overview(self, days: int = 30) -> dict:
        safety = await self._safety.status()
        research = await self._research.status()
        research_d = research.to_dict()
        funnel = await self._funnel.funnel(days=days)
        cost = await self._cost.summary(days=days)
        trades = await self._trades.summary(days=days)
        risk = await self._risk.summary(days=days)
        promotion_ready = await self._readiness.ready_count()

        return {
            "days": days,
            "safety": {
                "invariants_ok": safety["invariants_ok"],
                "warnings": safety["warnings"],
                # 다이제스트가 paper/test vs 실거래를 구분해 문구를 정하도록 추가(additive).
                "real_trading_enabled": safety["real_trading_enabled"],
                "auto_trade_versions": safety["auto_trade_versions"],
            },
            "research": {
                "pending_total": research_d["pending"]["total"],
                "active_strategy_versions": research_d["active"]["strategy_versions"],
                "active_scanner_versions": research_d["active"]["scanner_versions"],
                "disclosure_alerts": research_d["disclosure_alerts"],
                "macro_regime": research_d["macro"].get("regime"),
                "promotion_ready": promotion_ready,
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
                "budget_status": cost["budget"]["status"],
                "budget_used_pct": cost["budget"]["used_pct"],
            },
            "trading": {
                "closed_trades": trades["overall"]["closed"],
                "win_rate": trades["overall"]["win_rate"],
                "total_pnl": trades["overall"]["total_pnl"],
                "risk_rejected": risk["rejected"],
                "risk_rejection_rate": risk["rejection_rate"],
            },
        }
