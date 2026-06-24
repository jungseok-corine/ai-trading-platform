"""Status Transition Planner — 제안 승인 시 안전한 버전 상태 전환 계획 생성 (C-2.29.1).

deterministic rule-based planner다. LLM을 호출하지 않는다.

⚠️ 안전 원칙:
- 이 서비스는 상태 변경을 직접 수행하지 않는다. 계획을 생성하고 검증할 뿐이다.
- ACTIVE 버전 자동 생성 금지
- RUNNING experiment variant archive 금지
- 이전 버전 DRAFT 강등 금지
- 실주문 API 호출 금지
- 자동매매 플래그 변경 금지
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import ScannerRuleStatus, StrategyVersionStatus
from app.domain.repositories.experiment import ExperimentVariantRepository
from app.domain.repositories.scanner import ScannerRuleVersionRepository
from app.domain.repositories.scanner_proposal import ScannerRuleProposalRepository
from app.domain.repositories.strategy import StrategyVersionRepository
from app.domain.repositories.strategy_proposal import StrategyProposalRepository

ProposalType = Literal["strategy", "scanner"]
ProposedAction = Literal["KEEP", "ARCHIVE"]


@dataclass
class NewVersionPlan:
    status: str
    auto_trade_enabled: bool | None  # None for scanner (no auto_trade)
    reason: str


@dataclass
class VersionActionPlan:
    version_id: int
    current_status: str
    proposed_action: ProposedAction
    reason: str
    running_experiment_ids: list[int] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)


@dataclass
class BlockedAction:
    action: str
    version_id: int
    reason: str


@dataclass
class StatusTransitionPlan:
    proposal_id: int
    proposal_type: ProposalType
    new_version: NewVersionPlan
    previous_versions: list[VersionActionPlan]
    blocked_actions: list[BlockedAction]
    safety_warnings: list[str]
    plan_valid: bool

    def to_dict(self) -> dict:
        nv = {
            "status": self.new_version.status,
            "reason": self.new_version.reason,
        }
        if self.new_version.auto_trade_enabled is not None:
            nv["auto_trade_enabled"] = self.new_version.auto_trade_enabled
        return {
            "proposal_id": self.proposal_id,
            "proposal_type": self.proposal_type,
            "new_version": nv,
            "previous_versions": [
                {
                    "version_id": v.version_id,
                    "current_status": v.current_status,
                    "proposed_action": v.proposed_action,
                    "reason": v.reason,
                    "running_experiment_ids": v.running_experiment_ids,
                    "roles": v.roles,
                }
                for v in self.previous_versions
            ],
            "blocked_actions": [
                {
                    "action": b.action,
                    "version_id": b.version_id,
                    "reason": b.reason,
                }
                for b in self.blocked_actions
            ],
            "safety_warnings": self.safety_warnings,
            "plan_valid": self.plan_valid,
        }


class PlannerProposalNotFoundError(Exception):
    """proposal_id가 존재하지 않을 때."""


class StatusTransitionPlannerService:
    """제안 승인 전 안전한 버전 상태 전환 계획을 생성한다 (deterministic, no LLM).

    이 서비스는 상태를 변경하지 않는다. 계획을 생성하고 validate()로 검증할 뿐이다.
    실제 버전 생성은 ProposalService.approve() / ScannerProposalService.approve()가 담당한다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._strategy_proposal_repo = StrategyProposalRepository(session)
        self._scanner_proposal_repo = ScannerRuleProposalRepository(session)
        self._version_repo = StrategyVersionRepository(session)
        self._scanner_version_repo = ScannerRuleVersionRepository(session)
        self._variant_repo = ExperimentVariantRepository(session)

    async def plan_for_strategy_proposal(
        self, proposal_id: int
    ) -> StatusTransitionPlan:
        """전략 제안 승인 시의 상태 전환 계획을 생성한다."""
        proposal = await self._strategy_proposal_repo.get(proposal_id)
        if proposal is None:
            raise PlannerProposalNotFoundError(proposal_id)

        # 신규 버전은 TESTING으로 생성 (DRAFT 금지)
        new_version_plan = NewVersionPlan(
            status=StrategyVersionStatus.TESTING.value,
            auto_trade_enabled=False,
            reason="default safe status for approved strategy proposals",
        )

        # 같은 전략의 기존 버전들 분석
        existing_versions = await self._version_repo.list_by_strategy(
            proposal.strategy_id, include_archived=False
        )
        version_plans: list[VersionActionPlan] = []
        blocked: list[BlockedAction] = []
        warnings: list[str] = []

        for v in existing_versions:
            running_variants = await self._variant_repo.list_running_for_strategy_version(v.id)
            running_ids = [rv.experiment_id for rv in running_variants]
            roles = [rv.role.value for rv in running_variants]

            reason_parts: list[str] = []
            if v.status == StrategyVersionStatus.ACTIVE:
                reason_parts.append("ACTIVE version is kept unchanged; automatic replacement is forbidden")
                warnings.append(
                    f"version {v.id} is ACTIVE — it will remain unchanged; "
                    "real trading status is human-managed only"
                )
            if running_ids:
                role_str = ", ".join(roles) if roles else "variant"
                reason_parts.append(
                    f"attached to running experiment(s) {running_ids} as {role_str}"
                )
                blocked.append(
                    BlockedAction(
                        action="ARCHIVE_VERSION",
                        version_id=v.id,
                        reason=f"attached to running experiment (experiment_id={running_ids[0]})",
                    )
                )
                if roles:
                    warnings.append(
                        f"version {v.id} is {'/'.join(r.upper() for r in roles)} "
                        f"in running experiment {running_ids[0]} — archive is blocked"
                    )
            if not reason_parts:
                reason_parts.append("previous versions are not modified by default")

            version_plans.append(
                VersionActionPlan(
                    version_id=v.id,
                    current_status=v.status.value,
                    proposed_action="KEEP",
                    reason="; ".join(reason_parts),
                    running_experiment_ids=running_ids,
                    roles=roles,
                )
            )

        plan = StatusTransitionPlan(
            proposal_id=proposal_id,
            proposal_type="strategy",
            new_version=new_version_plan,
            previous_versions=version_plans,
            blocked_actions=blocked,
            safety_warnings=warnings,
            plan_valid=True,
        )
        return self.validate(plan)

    async def plan_for_scanner_proposal(
        self, proposal_id: int
    ) -> StatusTransitionPlan:
        """스캐너 제안 승인 시의 상태 전환 계획을 생성한다."""
        proposal = await self._scanner_proposal_repo.get(proposal_id)
        if proposal is None:
            raise PlannerProposalNotFoundError(proposal_id)

        new_version_plan = NewVersionPlan(
            status=ScannerRuleStatus.TESTING.value,
            auto_trade_enabled=None,  # 스캐너 버전에는 auto_trade 없음
            reason="default safe status for approved scanner proposals",
        )

        existing_versions = await self._scanner_version_repo.list_by_rule(
            proposal.scanner_rule_id
        )
        version_plans: list[VersionActionPlan] = []
        warnings: list[str] = []

        for v in existing_versions:
            reason_parts: list[str] = []
            if v.status == ScannerRuleStatus.ACTIVE:
                reason_parts.append("ACTIVE version is kept unchanged; automatic replacement is forbidden")
                warnings.append(
                    f"version {v.id} is ACTIVE — it will remain unchanged"
                )
            if not reason_parts:
                reason_parts.append("previous versions are not modified by default")

            version_plans.append(
                VersionActionPlan(
                    version_id=v.id,
                    current_status=v.status.value,
                    proposed_action="KEEP",
                    reason="; ".join(reason_parts),
                )
            )

        plan = StatusTransitionPlan(
            proposal_id=proposal_id,
            proposal_type="scanner",
            new_version=new_version_plan,
            previous_versions=version_plans,
            blocked_actions=[],
            safety_warnings=warnings,
            plan_valid=True,
        )
        return self.validate(plan)

    def validate(self, plan: StatusTransitionPlan) -> StatusTransitionPlan:
        """안전 규칙을 검사하고 plan_valid를 설정한다.

        R-1/R-2: 신규 버전은 TESTING이어야 한다.
        R-3:     신규 strategy 버전의 auto_trade_enabled는 False여야 한다.
        R-9:     ACTIVE 신규 생성 금지.
        R-5:     previous_versions에서 DRAFT 강등 시도 금지.
        """
        valid = True
        issues: list[str] = []

        # R-1/R-2: 신규 버전 status 검증
        valid_new_statuses = {
            StrategyVersionStatus.TESTING.value,
            ScannerRuleStatus.TESTING.value,
        }
        if plan.new_version.status not in valid_new_statuses:
            valid = False
            issues.append(
                f"new version status must be TESTING, got {plan.new_version.status!r}"
            )

        # R-9: ACTIVE 신규 생성 금지
        if plan.new_version.status in (
            StrategyVersionStatus.ACTIVE.value,
            ScannerRuleStatus.ACTIVE.value,
        ):
            valid = False
            issues.append("new version must not be ACTIVE — automatic ACTIVE creation is forbidden")

        # R-3: strategy 신규 버전의 auto_trade_enabled 검증
        if plan.proposal_type == "strategy":
            if plan.new_version.auto_trade_enabled is not False:
                valid = False
                issues.append(
                    "strategy new_version.auto_trade_enabled must be False"
                )

        # R-5: 이전 버전 DRAFT 강등 금지
        for vp in plan.previous_versions:
            if vp.proposed_action != "KEEP" and vp.current_status != vp.proposed_action:
                if vp.proposed_action == StrategyVersionStatus.DRAFT.value:
                    valid = False
                    issues.append(
                        f"version {vp.version_id}: downgrade to DRAFT is forbidden"
                    )

        if not valid and issues:
            plan.safety_warnings.extend(issues)
        plan.plan_valid = valid
        return plan
