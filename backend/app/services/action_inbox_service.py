"""Action Inbox v1 — 검토가 필요한 항목을 기존 read-only 소스에서 모은다.

승인/거절·잡 토글·실거래 동작이 전혀 없는 **읽기 전용 집계**다. 어떤 상태도 바꾸지 않는다.
사람이 '무엇을 봐야 하는지'를 한곳에서 보고, 각 전용 화면으로 이동하도록 돕는 용도다(v1).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import ProposalStatus
from app.domain.repositories.candidate_event import CandidateEventRepository
from app.domain.repositories.scanner_proposal import ScannerRuleProposalRepository
from app.domain.repositories.strategy_proposal import StrategyProposalRepository
from app.services.data_freshness_service import DataFreshnessService
from app.services.scheduler_health_service import SchedulerHealthService

# 심각도 정렬용 (높을수록 위로).
_SEVERITY_ORDER = {"info": 0, "attention": 1, "alert": 2}

# 후보 종목 인박스 노출 정책 (read-only, 노이즈 방지).
_CANDIDATE_RECENT_HOURS = 24  # 최근 N시간 내 발견된 후보만 본다.
_CANDIDATE_SCORE_THRESHOLD = 70  # 고점수 우선 노출 기준.
_CANDIDATE_MAX_ITEMS = 5  # 최대 노출 개수(스팸 방지).


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

        # 5) 최근 발견된 후보 종목 (read-only — 검토는 '후보 종목' 화면에서 사람만)
        items.extend(await self._candidate_items())

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

    async def _candidate_items(self) -> list[ActionInboxItem]:
        """최근 발견된 후보 종목을 인박스 항목으로 변환한다 (read-only).

        정책:
        - 최근 N시간 내 발견된 후보만 본다(오래된 건 노이즈).
        - 그중 고점수(>= 임계) 후보가 있으면 그것만, 없으면 최근 후보 그대로 노출.
        - 최대 개수로 캡(스팸 방지). 각 항목은 '후보 종목' 화면으로 이동만 가능.
        """
        repo = CandidateEventRepository(self._session)
        # 최신순으로 충분히 넉넉히 가져와 파이썬에서 시간/점수 필터링.
        recent_pool = await repo.list_filtered(limit=50)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=_CANDIDATE_RECENT_HOURS)
        recent = [c for c in recent_pool if self._aware(c.triggered_at) >= cutoff]
        if not recent:
            return []

        high = [c for c in recent if (c.score or 0) >= _CANDIDATE_SCORE_THRESHOLD]
        selected = (high if high else recent)[:_CANDIDATE_MAX_ITEMS]

        out: list[ActionInboxItem] = []
        for c in selected:
            matched = len(c.matched_conditions or [])
            out.append(ActionInboxItem(
                id=f"candidate_event:{c.id}",
                type="candidate_event",
                severity="attention",
                title=f"후보 종목 발견: {c.symbol_code}",
                description=f"점수 {c.score or 0}, 조건 {matched}개",
                source="candidate_events",
                as_of=self._aware(c.triggered_at).isoformat(),
                related_url="research:candidates",
                related_id=c.id,
            ))
        return out

    @staticmethod
    def _aware(dt: datetime) -> datetime:
        """naive datetime은 UTC로 간주해 비교/직렬화 안전하게 만든다."""
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
