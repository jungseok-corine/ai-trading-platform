"""Pair-Scoped Recurring Signal Run Plan — schema + inert plan management (M2.14A).

D-24를 따른다: 상시 신호 운영은 **명시한 baseline+challenger 페어** 한정, `max_runs` 상한,
**SignalLog-only** 반복 *계획*부터 시작한다. 전역 런너 활성은 V1이 아니다.

핵심 안전 불변식 (M2.14A 범위 — **계획만 관리, 실행 없음**):
- 계획은 항상 `status="prepared"`로 생성된다. **active 계획을 만들지 않는다.**
- **어떤 SignalLog/Trade/Order도 만들지 않는다.** 디스패처/run-loop/스케줄러 통합 없음(M2.14B 별도 승인).
- 생성/중지/조회만 한다. 계획은 실행되지 않는다(inert) — `next_run_at`은 항상 NULL.
- 자격 검증은 M2.8 `PaperSignalSessionRunOnceService`의 게이트/검증 코어를 재사용한다(드리프트 방지):
  `check_confirmation`, `check_global_gates`(실거래 OFF + 상시 런너 OFF), `validate_session`(active +
  버전 존재 + DRAFT + auto_trade off + 등록 strategy_type + symbol). 이들은 **SignalLog를 만들지 않는다.**
- 페어 관계 검증은 M2.10과 동일 규칙/예외(source_type · baseline 일치 · symbol 일치)를 재사용한다.
- PaperSignalSession/StrategyVersion/StrategyProposal status를 바꾸지 않는다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.paper_signal_recurring_run import (
    PaperSignalRecurringRunRepository,
)
from app.domain.repositories.paper_signal_session import PaperSignalSessionRepository
from app.services.paper_signal_pair_run_once_service import (
    BaselineMismatchError,
    NotChallengerSessionError,
    SymbolMismatchError,
)
from app.services.paper_signal_run_once_service import PaperSignalSessionRunOnceService

# 허용 범위 (문서화된 값). interval은 과도한 폴링·과소 누적을 피하는 구간, max_runs는 누적 상한.
MIN_INTERVAL_SECONDS = 60
MAX_INTERVAL_SECONDS = 3600
MIN_MAX_RUNS = 1
MAX_MAX_RUNS = 390  # 정규장 1분봉 1세션 분량 상한 근사(범위 상한 가드).

# 상태별 경고 — 어떤 단계도 SignalLog/주문/거래를 만들지 않음을 명시(표시 전용).
_PREPARED_WARNINGS = [
    "This plan is prepared only and does not run yet.",
    "No SignalLogs are created until an explicitly approved future dispatcher exists.",
    "No orders or trades are created.",
]
_ACTIVE_WARNINGS = [
    "This plan is active but no dispatcher exists in this phase.",
    "No SignalLogs are created by activation.",
    "No orders or trades are created.",
]
_TERMINAL_WARNINGS = [
    "This plan is no longer running.",
    "No SignalLogs are created.",
    "No orders or trades are created.",
]


def _warnings_for(status: str) -> list[str]:
    if status == "prepared":
        return list(_PREPARED_WARNINGS)
    if status == "active":
        return list(_ACTIVE_WARNINGS)
    return list(_TERMINAL_WARNINGS)


class RecurringConfirmationRequiredError(Exception):
    """confirmed/confirmed_by(또는 created_by) 누락 (422)."""


class RecurringBaselineNotFoundError(Exception):
    """baseline_session_id 미존재 (404)."""


class RecurringChallengerNotFoundError(Exception):
    """challenger_session_id 미존재 (404)."""


class RecurringInvalidIntervalError(Exception):
    """interval_seconds 범위 밖 (422)."""


class RecurringInvalidMaxRunsError(Exception):
    """max_runs 범위 밖 (422)."""


class DuplicateRecurringPlanError(Exception):
    """같은 페어에 비종료(prepared/active) 계획이 이미 있음 (409)."""


class RecurringPlanNotFoundError(Exception):
    """plan id 미존재 (404)."""


class RecurringPlanNotStoppableError(Exception):
    """종료(stopped/completed/failed) 계획 중지 시도 (422). prepared/active만 중지 가능."""


class RecurringPlanNotActivatableError(Exception):
    """prepared가 아닌 계획 활성화 시도 (422). prepared만 active로 전환 가능."""


class PaperSignalRecurringRunService:
    """pair-scoped 반복 신호 *계획*을 생성·중지·조회한다(실행 없음, SignalLog 없음)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = PaperSignalRecurringRunRepository(session)
        self._session_repo = PaperSignalSessionRepository(session)
        # 검증 전용으로 M2.8 코어를 재사용한다. evaluate/run은 절대 호출하지 않으므로
        # signal_service가 필요 없다(None). validate_session/check_* 는 SignalLog를 만들지 않는다.
        self._validator = PaperSignalSessionRunOnceService(session, signal_service=None)

    # --- shared validation --------------------------------------------------

    async def _load_and_validate_pair(
        self, baseline_session_id: int, challenger_session_id: int
    ):
        """세션 존재 + 페어 관계(M2.10) + 두 세션 자격(M2.8 validate_session)을 검증한다.

        create/activate가 공유한다(검증 드리프트 방지). **SignalLog/주문을 만들지 않는다**
        (validate_session은 버전/전략을 읽고 검증만 한다). 반환: (baseline, challenger).
        """
        baseline = await self._session_repo.get(baseline_session_id)
        if baseline is None:
            raise RecurringBaselineNotFoundError(baseline_session_id)
        challenger = await self._session_repo.get(challenger_session_id)
        if challenger is None:
            raise RecurringChallengerNotFoundError(challenger_session_id)
        # 페어 관계 게이트(M2.10과 동일 규칙/예외).
        if challenger.source_type != "signal_challenger":
            raise NotChallengerSessionError(
                f"challenger {challenger_session_id} source_type is "
                f"{challenger.source_type!r}, not signal_challenger"
            )
        if challenger.baseline_session_id != baseline_session_id:
            raise BaselineMismatchError(
                f"challenger {challenger_session_id} baseline_session_id "
                f"{challenger.baseline_session_id} != provided baseline {baseline_session_id}"
            )
        if baseline.symbol_code != challenger.symbol_code:
            raise SymbolMismatchError(
                f"symbol mismatch: baseline {baseline.symbol_code!r} != "
                f"challenger {challenger.symbol_code!r}"
            )
        # 두 세션 자격(active + 버전 DRAFT + auto_trade off + 등록 strategy_type + symbol).
        await self._validator.validate_session(baseline)
        await self._validator.validate_session(challenger)
        return baseline, challenger

    # --- create -------------------------------------------------------------

    async def create_prepared_pair_plan(
        self,
        baseline_session_id: int,
        challenger_session_id: int,
        interval_seconds: int,
        max_runs: int,
        confirmed: bool,
        confirmed_by: str | None,
        note: str | None = None,
    ) -> dict:
        # 1) 사람 확인 게이트.
        if not confirmed:
            raise RecurringConfirmationRequiredError("confirmed must be true")
        if not confirmed_by:
            raise RecurringConfirmationRequiredError("confirmed_by is required")

        # 2) 전역 안전 게이트(실거래 OFF + 상시 런너 OFF). M2.8 코어 재사용.
        self._validator.check_global_gates()

        # 3) 파라미터 범위.
        if not (MIN_INTERVAL_SECONDS <= interval_seconds <= MAX_INTERVAL_SECONDS):
            raise RecurringInvalidIntervalError(
                f"interval_seconds must be in [{MIN_INTERVAL_SECONDS}, {MAX_INTERVAL_SECONDS}]"
            )
        if not (MIN_MAX_RUNS <= max_runs <= MAX_MAX_RUNS):
            raise RecurringInvalidMaxRunsError(
                f"max_runs must be in [{MIN_MAX_RUNS}, {MAX_MAX_RUNS}]"
            )

        # 4~6) 세션 존재 + 페어 관계(M2.10) + 두 세션 자격(M2.8 validate_session). 활성화와 동일
        #       검증 재사용(드리프트 방지). SignalLog/주문 생성 없음(읽기·검증만).
        await self._load_and_validate_pair(baseline_session_id, challenger_session_id)

        # 7) 중복 비종료 계획 가드(서비스 레벨).
        existing = await self._repo.find_open_for_pair(
            baseline_session_id, challenger_session_id
        )
        if existing is not None:
            raise DuplicateRecurringPlanError(
                f"a non-terminal recurring plan (id={existing.id}, status={existing.status}) "
                f"already exists for this pair"
            )

        # 8) prepared 계획 생성(inert). next_run_at=NULL(스케줄 없음).
        plan = await self._repo.create(
            status="prepared",
            scope_type="baseline_challenger_pair",
            baseline_session_id=baseline_session_id,
            challenger_session_id=challenger_session_id,
            interval_seconds=interval_seconds,
            max_runs=max_runs,
            completed_runs=0,
            next_run_at=None,
            created_by=confirmed_by,
            note=note,
        )
        await self._session.commit()
        return self._to_dict(plan)

    # --- activate (M2.14B-1: 상태 전환만 — 실행 아님) -----------------------

    async def activate_plan(
        self, plan_id: int, confirmed: bool, confirmed_by: str | None
    ) -> dict:
        """prepared 계획을 active로 전환한다. **활성화는 실행이 아니다**:

        - 디스패처/잡/스케줄러를 시작하지 않는다. SignalLog/주문/거래를 만들지 않는다.
        - active = "미래에 별도 승인될 디스패처의 후보 상태"일 뿐(M2.14B-2 별도 승인).
        - next_run_at은 미래 디스패처용 메타데이터로만 설정한다(이 단계에선 아무도 읽지 않는다).
        """
        if not confirmed:
            raise RecurringConfirmationRequiredError("confirmed must be true")
        if not confirmed_by:
            raise RecurringConfirmationRequiredError("confirmed_by is required")
        # 전역 안전 게이트(실거래 OFF + 상시 런너 OFF). M2.8 코어 재사용.
        self._validator.check_global_gates()
        plan = await self._repo.get(plan_id)
        if plan is None:
            raise RecurringPlanNotFoundError(plan_id)
        if plan.status != "prepared":
            raise RecurringPlanNotActivatableError(
                f"plan {plan_id} status is {plan.status!r}; only prepared plans are activatable"
            )
        # 활성화 시점 재검증(생성 이후 세션/버전 상태가 바뀌었을 수 있다).
        await self._load_and_validate_pair(
            plan.baseline_session_id, plan.challenger_session_id
        )
        # 같은 페어에 또 다른 active 계획이 있으면 거부(자기 자신 제외).
        other_active = await self._repo.find_active_for_pair(
            plan.baseline_session_id, plan.challenger_session_id, exclude_id=plan.id
        )
        if other_active is not None:
            raise DuplicateRecurringPlanError(
                f"an active recurring plan (id={other_active.id}) already exists for this pair"
            )
        now = datetime.now(timezone.utc)
        await self._repo.update(
            plan,
            status="active",
            # 미래 디스패처용 메타데이터일 뿐 — 이 단계에선 실행/스케줄 트리거가 없다.
            next_run_at=now + timedelta(seconds=plan.interval_seconds),
        )
        await self._session.commit()
        return self._to_dict(plan)

    # --- stop / read --------------------------------------------------------

    async def stop_plan(
        self, plan_id: int, confirmed: bool, confirmed_by: str | None
    ) -> dict:
        if not confirmed:
            raise RecurringConfirmationRequiredError("confirmed must be true")
        if not confirmed_by:
            raise RecurringConfirmationRequiredError("confirmed_by is required")
        plan = await self._repo.get(plan_id)
        if plan is None:
            raise RecurringPlanNotFoundError(plan_id)
        # M2.14B-1: prepared/active 모두 중지 가능. 이미 종료된 계획 중지는 거부(명시적 422).
        if plan.status not in ("prepared", "active"):
            raise RecurringPlanNotStoppableError(
                f"plan {plan_id} status is {plan.status!r}; only prepared/active plans are stoppable"
            )
        await self._repo.update(
            plan,
            status="stopped",
            stopped_by=confirmed_by,
            stopped_at=datetime.now(timezone.utc),
            next_run_at=None,  # 중지 시 미래 스케줄 메타데이터 제거.
        )
        await self._session.commit()
        return self._to_dict(plan)

    async def get_plan(self, plan_id: int) -> dict:
        plan = await self._repo.get(plan_id)
        if plan is None:
            raise RecurringPlanNotFoundError(plan_id)
        return self._to_dict(plan)

    async def list_plans(
        self, status: str | None = None, limit: int = 200, offset: int = 0
    ) -> list[dict]:
        plans = await self._repo.list_filtered(status=status, limit=limit, offset=offset)
        return [self._to_dict(p) for p in plans]

    # --- serialization ------------------------------------------------------

    @staticmethod
    def _to_dict(plan) -> dict:
        return {
            "id": plan.id,
            "status": plan.status,
            "scope_type": plan.scope_type,
            "baseline_session_id": plan.baseline_session_id,
            "challenger_session_id": plan.challenger_session_id,
            "interval_seconds": plan.interval_seconds,
            "max_runs": plan.max_runs,
            "completed_runs": plan.completed_runs,
            "last_run_at": plan.last_run_at,
            "next_run_at": plan.next_run_at,
            "created_by": plan.created_by,
            "stopped_by": plan.stopped_by,
            "stopped_at": plan.stopped_at,
            "note": plan.note,
            "last_error": plan.last_error,
            "orders_created": 0,  # 항상 0 (이 단계는 실행하지 않음)
            "trades_created": 0,  # 항상 0
            "warnings": _warnings_for(plan.status),
        }


__all__ = [
    "PaperSignalRecurringRunService",
    "MIN_INTERVAL_SECONDS",
    "MAX_INTERVAL_SECONDS",
    "MIN_MAX_RUNS",
    "MAX_MAX_RUNS",
    "RecurringConfirmationRequiredError",
    "RecurringBaselineNotFoundError",
    "RecurringChallengerNotFoundError",
    "RecurringInvalidIntervalError",
    "RecurringInvalidMaxRunsError",
    "DuplicateRecurringPlanError",
    "RecurringPlanNotFoundError",
    "RecurringPlanNotStoppableError",
    "RecurringPlanNotActivatableError",
]
