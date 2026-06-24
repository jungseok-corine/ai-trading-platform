"""Action Inbox v1 — 검토가 필요한 항목을 기존 read-only 소스에서 모은다.

승인/거절·잡 토글·실거래 동작이 전혀 없는 **읽기 전용 집계**다. 어떤 상태도 바꾸지 않는다.
사람이 '무엇을 봐야 하는지'를 한곳에서 보고, 각 전용 화면으로 이동하도록 돕는 용도다(v1).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import ProposalStatus
from app.domain.repositories.scanner_proposal import ScannerRuleProposalRepository
from app.domain.repositories.strategy_proposal import StrategyProposalRepository
from app.services.data_freshness_service import DataFreshnessService
from app.services.scheduler_health_service import SchedulerHealthService

# 심각도 정렬용 (높을수록 위로).
_SEVERITY_ORDER = {"info": 0, "attention": 1, "alert": 2}


@dataclass
class ActionInboxItem:
    id: str
    type: str
    severity: str  # info | attention | alert
    title: str
    description: str
    source: str
    as_of: str
    related_url: str | None = None  # 프론트가 해석하는 섹션 키(네비게이션 힌트). v1은 표시만.
    related_id: int | None = None
    dismissible: bool = False  # v1: 항상 False (조치 버튼 없음)


class ActionInboxService:
    """검토 대기 항목을 모은다 (v1, read-only). 어떤 쓰기/승인/토글도 하지 않는다."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def items(self) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        items: list[ActionInboxItem] = []

        # 1) 검토 대기 전략 제안 (승인은 사람만 — 여기선 카운트/네비게이션만)
        pending_strategy = await StrategyProposalRepository(self._session).list_filtered(
            status=ProposalStatus.PENDING, limit=500
        )
        if pending_strategy:
            items.append(ActionInboxItem(
                id="pending_strategy_proposals",
                type="strategy_proposal",
                severity="attention",
                title=f"검토 대기 전략 제안 {len(pending_strategy)}건",
                description="AI/수동 전략 개선 제안이 검토를 기다립니다. 승인은 사람만 합니다.",
                source="strategy_proposals",
                as_of=now,
                related_url="research:proposals",
            ))

        # 2) 검토 대기 스캐너 제안
        pending_scanner = await ScannerRuleProposalRepository(self._session).list_filtered(
            status=ProposalStatus.PENDING, limit=500
        )
        if pending_scanner:
            items.append(ActionInboxItem(
                id="pending_scanner_proposals",
                type="scanner_proposal",
                severity="attention",
                title=f"검토 대기 스캐너 제안 {len(pending_scanner)}건",
                description="스캐너 룰 개선 제안이 검토를 기다립니다. 승인은 사람만 합니다.",
                source="scanner_proposals",
                as_of=now,
                related_url="research:scanner-proposals",
            ))

        # 3) 자율 잡 이상 (실행 기록 없음/실패/지연 — read-only 점검)
        health = await SchedulerHealthService(self._session).status()
        if health["unhealthy_count"]:
            jobs = ", ".join(health["unhealthy_jobs"])
            items.append(ActionInboxItem(
                id="unhealthy_jobs",
                type="scheduler_health",
                severity="alert",
                title=f"자율 잡 점검 필요 {health['unhealthy_count']}건",
                description=f"점검이 필요한 잡: {jobs}",
                source="scheduler_health",
                as_of=now,
                related_url="research:autonomous-jobs",
            ))

        # 4) 데이터 신선도 (오래된 수집 소스)
        fresh = await DataFreshnessService(self._session).status()
        if fresh["stale_count"]:
            sources = ", ".join(fresh["stale_sources"])
            items.append(ActionInboxItem(
                id="stale_data_sources",
                type="data_freshness",
                severity="attention",
                title=f"오래된 데이터 소스 {fresh['stale_count']}개",
                description=f"수집 점검이 필요한 소스: {sources}",
                source="data_freshness",
                as_of=now,
                related_url="research:freshness",
            ))

        items.sort(key=lambda i: _SEVERITY_ORDER.get(i.severity, 0), reverse=True)
        counts = {
            "alert": sum(1 for i in items if i.severity == "alert"),
            "attention": sum(1 for i in items if i.severity == "attention"),
            "total": len(items),
        }
        return {
            "generated_at": now,
            "counts": counts,
            "items": [asdict(i) for i in items],
        }
