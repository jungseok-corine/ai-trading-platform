"""AI 의사결정 피드 (C-6.7).

"오늘 AI가 무엇을 분석했고, 무엇을 제안했고, 사람이 무엇을 결정했나"를
한 타임라인으로 조합한다. 기존 테이블의 read-only 집계 — 새 상태 없음.

이벤트 소스:
- ai_analysis_runs: LLM 분석 실행 (무엇을 대상으로, 결과 상태)
- strategy_proposals / scanner_rule_proposals: 제안 생성 + 사람 검토(승인/거절)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.ai_analysis import AiAnalysisRun
from app.domain.models.scanner_proposal import ScannerRuleProposal
from app.domain.models.strategy_proposal import StrategyProposal


class AiActivityFeedService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def feed(self, days: int = 1, limit: int = 100) -> dict[str, Any]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        events: list[dict[str, Any]] = []

        events += await self._analysis_runs(cutoff)
        events += await self._strategy_proposals(cutoff)
        events += await self._scanner_proposals(cutoff)

        events.sort(key=lambda e: e["ts"], reverse=True)
        return {
            "days": days,
            "count": len(events[:limit]),
            "events": events[:limit],
        }

    async def _analysis_runs(self, cutoff: datetime) -> list[dict[str, Any]]:
        stmt = (
            select(AiAnalysisRun)
            .where(AiAnalysisRun.created_at >= cutoff)
            .order_by(AiAnalysisRun.created_at.desc())
            .limit(50)
        )
        runs = (await self._session.execute(stmt)).scalars().all()
        return [
            {
                "ts": r.created_at.isoformat(),
                "kind": "analysis_run",
                "title": f"AI 분석 실행 #{r.id} ({r.provider}/{r.mode.value})",
                "detail": (
                    f"{r.target_type.value} {r.target_id} 대상 — {r.status.value}"
                    + (f", 전략버전 v{r.strategy_version_id}" if r.strategy_version_id else "")
                ),
                "ref": {"type": "analysis_run", "id": r.id},
            }
            for r in runs
        ]

    async def _strategy_proposals(self, cutoff: datetime) -> list[dict[str, Any]]:
        stmt = (
            select(StrategyProposal)
            .where(StrategyProposal.created_at >= cutoff)
            .order_by(StrategyProposal.created_at.desc())
            .limit(50)
        )
        proposals = (await self._session.execute(stmt)).scalars().all()
        events: list[dict[str, Any]] = []
        for p in proposals:
            bt = p.backtest_summary or {}
            verdict = bt.get("verdict")
            events.append(
                {
                    "ts": p.created_at.isoformat(),
                    "kind": "proposal_created",
                    "title": f"전략 제안 #{p.id} 생성",
                    "detail": p.title + (f" — 백테스트: {verdict}" if verdict else ""),
                    "ref": {"type": "strategy_proposal", "id": p.id},
                }
            )
        # 사람 검토 이벤트 (승인/거절) — 생성 윈도우 밖 제안이라도 검토가 최근이면 포함
        reviewed_stmt = (
            select(StrategyProposal)
            .where(StrategyProposal.reviewed_at >= cutoff)
            .order_by(StrategyProposal.reviewed_at.desc())
            .limit(50)
        )
        for p in (await self._session.execute(reviewed_stmt)).scalars().all():
            events.append(
                {
                    "ts": p.reviewed_at.isoformat(),
                    "kind": f"proposal_{p.status.value}",
                    "title": f"전략 제안 #{p.id} {'승인' if p.status.value == 'approved' else '거절'}",
                    "detail": p.title
                    + (f" → 새 버전 v{p.created_version_id}" if p.created_version_id else ""),
                    "ref": {"type": "strategy_proposal", "id": p.id},
                }
            )
        return events

    async def _scanner_proposals(self, cutoff: datetime) -> list[dict[str, Any]]:
        stmt = (
            select(ScannerRuleProposal)
            .where(ScannerRuleProposal.created_at >= cutoff)
            .order_by(ScannerRuleProposal.created_at.desc())
            .limit(50)
        )
        events: list[dict[str, Any]] = [
            {
                "ts": p.created_at.isoformat(),
                "kind": "scanner_proposal_created",
                "title": f"스캐너 제안 #{p.id} 생성",
                "detail": p.title,
                "ref": {"type": "scanner_proposal", "id": p.id},
            }
            for p in (await self._session.execute(stmt)).scalars().all()
        ]
        reviewed_stmt = (
            select(ScannerRuleProposal)
            .where(ScannerRuleProposal.reviewed_at >= cutoff)
            .order_by(ScannerRuleProposal.reviewed_at.desc())
            .limit(50)
        )
        for p in (await self._session.execute(reviewed_stmt)).scalars().all():
            events.append(
                {
                    "ts": p.reviewed_at.isoformat(),
                    "kind": f"scanner_proposal_{p.status.value}",
                    "title": f"스캐너 제안 #{p.id} {'승인' if p.status.value == 'approved' else '거절'}",
                    "detail": p.title,
                    "ref": {"type": "scanner_proposal", "id": p.id},
                }
            )
        return events
