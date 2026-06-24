"""실전 승격 심사 게이트 서비스 (C-2.29).

이 서비스는 paper 전략이 실전 검토 기준을 통과했는지 평가하고,
사람이 명시적으로 승인했다는 감사 로그(LivePromotionRecord)를 남긴다.

⚠️ 안전 원칙 — 아래 항목은 이 서비스 어디서도 수행하지 않는다:
- StrategyVersion.status 변경 금지
- 자동매매 플래그(auto trade) 변경 금지
- 실전 거래 활성화 환경변수(real trading flag) 변경 금지
- 실주문 API·실주문 함수 호출 금지
- 실계좌 자동 연결 금지
- AI 자동 승인 금지
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.intelligence_strategy_proposal import IntelligenceStrategyProposal
from app.domain.models.promotion import LivePromotionRecord
from app.domain.models.strategy import StrategyVersion
from app.domain.models.strategy_proposal import StrategyProposal
from app.domain.repositories.promotion import (
    LivePromotionRecordRepository,
    PromotionCriteriaRepository,
    PromotionEvaluationRepository,
)
from app.domain.repositories.strategy import StrategyVersionRepository
from app.services.promotion_service import PromotionResult, PromotionService


class LivePromotionVersionNotFoundError(Exception):
    """strategy_version_id가 존재하지 않을 때."""


class LivePromotionCriteriaNotFoundError(Exception):
    """사용 가능한 PromotionCriteria가 없을 때."""


class LivePromotionReadinessFailedError(Exception):
    """승격 기준을 통과하지 못했을 때."""

    def __init__(self, failed_checks: list[str]) -> None:
        self.failed_checks = failed_checks
        super().__init__(f"readiness checks failed: {failed_checks}")


class LivePromotionAlreadyApprovedError(Exception):
    """이미 approved 레코드가 존재할 때 (중복 승인 방지)."""


class LivePromotionNotConfirmedError(Exception):
    """confirmed=True 없이 호출할 때."""


@dataclass
class LiveReadinessReport:
    strategy_version_id: int
    criteria_id: int | None
    passed: bool
    trades_count: int
    days: int
    expectancy: float
    max_drawdown: float
    checks: list[dict] = field(default_factory=list)
    intel_context: dict | None = None
    evaluation_id: int | None = None

    def to_dict(self) -> dict:
        return {
            "strategy_version_id": self.strategy_version_id,
            "criteria_id": self.criteria_id,
            "passed": self.passed,
            "trades_count": self.trades_count,
            "days": self.days,
            "expectancy": float(self.expectancy),
            "max_drawdown": float(self.max_drawdown),
            "checks": self.checks,
            "intel_context": self.intel_context,
            "evaluation_id": self.evaluation_id,
        }


class LivePromotionGateService:
    """실전 승격 심사 게이트.

    check_readiness() — paper 전략의 실전 검토 기준 통과 여부를 평가한다.
    approve_live_promotion() — 사람의 명시적 승인을 감사 로그로 남긴다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._version_repo = StrategyVersionRepository(session)
        self._criteria_repo = PromotionCriteriaRepository(session)
        self._eval_repo = PromotionEvaluationRepository(session)
        self._record_repo = LivePromotionRecordRepository(session)
        self._promotion_svc = PromotionService(session)

    async def check_readiness(
        self,
        strategy_version_id: int,
        criteria_id: int | None = None,
    ) -> LiveReadinessReport:
        """승격 준비도를 평가하고 보고서를 반환한다."""
        version = await self._version_repo.get(strategy_version_id)
        if version is None:
            raise LivePromotionVersionNotFoundError(strategy_version_id)

        # 기준이 지정되지 않으면 활성화된 첫 번째 기준을 사용
        effective_criteria_id = criteria_id
        if effective_criteria_id is None:
            criteria_list = await self._criteria_repo.list_all()
            active = [c for c in criteria_list if c.enabled]
            if not active:
                raise LivePromotionCriteriaNotFoundError(
                    "no enabled PromotionCriteria found"
                )
            effective_criteria_id = active[0].id

        # PromotionService.evaluate() 를 사용해 기준 평가 (persist=True 로 스냅샷 저장)
        result: PromotionResult = await self._promotion_svc.evaluate(
            strategy_version_id, effective_criteria_id, persist=True
        )

        # 방금 저장된 PromotionEvaluation ID 조회
        evals = await self._eval_repo.list_by_version(strategy_version_id, limit=1)
        evaluation_id = evals[0].id if evals else None

        # Intelligence 컨텍스트 조회 (best-effort, 없어도 게이트 동작에 영향 없음)
        intel_context = await self._find_intel_context(strategy_version_id)

        return LiveReadinessReport(
            strategy_version_id=strategy_version_id,
            criteria_id=effective_criteria_id,
            passed=result.passed,
            trades_count=result.trades_count,
            days=result.days,
            expectancy=float(result.expectancy),
            max_drawdown=float(result.max_drawdown),
            checks=[c.to_dict() for c in result.checks],
            intel_context=intel_context,
            evaluation_id=evaluation_id,
        )

    async def approve_live_promotion(
        self,
        strategy_version_id: int,
        confirmed_by: str,
        note: str | None = None,
        confirmed: bool = False,
        criteria_id: int | None = None,
    ) -> LivePromotionRecord:
        """사람의 명시적 확인을 받아 실전 승격 심사 승인 로그를 생성한다.

        ⚠️ 이 메서드는 StrategyVersion.status, 자동매매 플래그,
        실전 거래 활성화 환경변수를 변경하지 않는다. 실주문도 하지 않는다.
        """
        if not confirmed:
            raise LivePromotionNotConfirmedError(
                "confirmed=True must be explicitly set to approve live promotion"
            )
        if not confirmed_by or not confirmed_by.strip():
            raise LivePromotionNotConfirmedError("confirmed_by must not be empty")

        version = await self._version_repo.get(strategy_version_id)
        if version is None:
            raise LivePromotionVersionNotFoundError(strategy_version_id)

        # 중복 승인 방지
        existing = await self._record_repo.find_approved(strategy_version_id)
        if existing is not None:
            raise LivePromotionAlreadyApprovedError(
                f"strategy_version_id={strategy_version_id} already has an approved record (id={existing.id})"
            )

        # 준비도 평가
        readiness = await self.check_readiness(strategy_version_id, criteria_id)
        if not readiness.passed:
            failed = [c["name"] for c in readiness.checks if not c["passed"]]
            raise LivePromotionReadinessFailedError(failed)

        readiness_snapshot = readiness.to_dict()

        record = await self._record_repo.create(
            strategy_version_id=strategy_version_id,
            promotion_evaluation_id=readiness.evaluation_id,
            status=LivePromotionRecord.STATUS_APPROVED,
            criteria_passed=readiness.passed,
            readiness_snapshot=readiness_snapshot,
            risk_snapshot=None,
            approved_at=datetime.now(timezone.utc),
            approved_by=confirmed_by.strip(),
            note=note,
        )
        await self._session.commit()
        return record

    async def _find_intel_context(self, strategy_version_id: int) -> dict | None:
        """IntelligenceStrategyProposal이 이 버전과 연관되어 있는지 조회한다 (best-effort)."""
        result = await self._session.execute(
            select(IntelligenceStrategyProposal)
            .join(
                StrategyProposal,
                IntelligenceStrategyProposal.evolution_strategy_proposal_id == StrategyProposal.id,
            )
            .where(StrategyProposal.base_version_id == strategy_version_id)
            .limit(1)
        )
        intel_proposal = result.scalar_one_or_none()
        if intel_proposal is None:
            return None
        return {
            "intel_proposal_id": intel_proposal.id,
            "experiment_id": intel_proposal.experiment_id,
            "evolution_status": intel_proposal.evolution_status,
            "symbol_code": intel_proposal.symbol_code,
            "market": intel_proposal.market.value if intel_proposal.market else None,
        }
