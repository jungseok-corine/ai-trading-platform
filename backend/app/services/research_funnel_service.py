from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.enums import ExperimentStatus
from app.domain.models.experiment import Experiment
from app.domain.models.strategy_assignment import StrategyAssignmentLog


class ResearchFunnelService:
    """연구 루프 전반부 퍼널 (C-3.21).

    제안 퍼널(C-3.2)이 'AI 제안→승인→버전→회고'(후반부)를 본다면, 이건 그 앞단
    '후보 포착→전략 배정→실험'을 본다. 시장 스캔이 실제로 실험으로 이어지는지(전환율)를
    가늠한다. read-only 집계 — 주문/외부 호출이 없다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def funnel(self, days: int = 30) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=max(1, days))

        candidates = await self._count(
            select(func.count(CandidateEvent.id)).where(CandidateEvent.created_at >= since)
        )
        assignments = await self._count(
            select(func.count(StrategyAssignmentLog.id))
            .where(StrategyAssignmentLog.created_at >= since)
        )
        candidates_assigned = await self._count(
            select(func.count(func.distinct(StrategyAssignmentLog.candidate_event_id)))
            .where(StrategyAssignmentLog.created_at >= since)
        )
        experiments = await self._count(
            select(func.count(Experiment.id)).where(Experiment.created_at >= since)
        )
        experiments_running = await self._count(
            select(func.count(Experiment.id)).where(
                Experiment.status == ExperimentStatus.RUNNING
            )
        )

        assignment_rate = (
            round(candidates_assigned / candidates, 3) if candidates else None
        )
        return {
            "days": days,
            "candidates": candidates,
            "assignments": assignments,
            "candidates_assigned": candidates_assigned,
            "assignment_rate": assignment_rate,
            "experiments": experiments,
            "experiments_running": experiments_running,
        }

    async def _count(self, stmt) -> int:
        return (await self._session.execute(stmt)).scalar() or 0
