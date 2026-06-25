"""Paper Signal Session 서비스 — paper 신호 기록(signal-only) 시작/중지/실행.

**구조적으로 주문을 낼 수 없다:**
- TradeService/주문 클라이언트를 구성하지도, 호출하지도 않는다.
- run_due_sessions는 SignalService.generate_and_log_signal만 호출한다(SignalLog만 기록).
- 연결된 StrategyVersion은 DRAFT 그대로 유지 → 기존 trade-capable runner는 절대 보지 못한다.
- StrategyVersion/Experiment 상태를 바꾸지 않는다. auto_trade_enabled를 켜지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.paper_signal_session import PaperSignalSession
from app.domain.repositories.candidate_strategy_proposal import (
    CandidateStrategyProposalRepository,
)
from app.domain.repositories.experiment import ExperimentVariantRepository
from app.domain.repositories.paper_signal_session import PaperSignalSessionRepository
from app.domain.repositories.strategy import StrategyVersionRepository
from app.services.candidate_proposal_experiment_service import _READY_AT_KEY
from app.services.signal_service import SignalService
from app.trading.strategy.registry import create_strategy


class ProposalNotFoundError(Exception):
    """candidate_strategy_proposal id가 존재하지 않을 때."""


class ProposalNotApprovedError(Exception):
    """APPROVED 상태가 아닌 제안으로 세션을 시작하려 할 때."""


class NotReadyError(Exception):
    """paper 준비 승인(readiness)이 없는 제안으로 세션을 시작하려 할 때."""


class NotPreparedError(Exception):
    """준비된 paper 실험(experiment_id)이 없는 제안일 때."""


class InvalidVersionStateError(Exception):
    """연결된 전략 버전이 없거나 DRAFT가 아닐 때(신호 세션은 DRAFT 전용)."""


class UnexpectedAutoTradeError(Exception):
    """연결된 전략 버전의 자동매매 토글이 켜져 있어 시작을 거부할 때(방어적)."""


class ConfirmationRequiredError(Exception):
    """confirmed=true / confirmed_by 없이 시작/중지하려 할 때."""


class DuplicateActiveSessionError(Exception):
    """같은 제안에 이미 active 세션이 있을 때."""


class SessionNotFoundError(Exception):
    """paper_signal_session id가 존재하지 않을 때."""


@dataclass
class RunSummary:
    checked: int
    signals_created: int
    skipped: int
    errors: list[str]

    def to_dict(self) -> dict:
        return {
            "checked": self.checked,
            "signals_created": self.signals_created,
            "skipped": self.skipped,
            "errors": self.errors,
        }


class PaperSignalService:
    def __init__(
        self, session: AsyncSession, signal_service: SignalService | None = None
    ) -> None:
        self._session = session
        # signal_service는 run_due_sessions에서만 필요(생성/중지에는 불필요).
        # TradeService는 받지 않는다 — 이 서비스는 주문 경로가 없다.
        self._signal_service = signal_service
        self._repo = PaperSignalSessionRepository(session)
        self._proposal_repo = CandidateStrategyProposalRepository(session)
        self._version_repo = StrategyVersionRepository(session)
        self._variant_repo = ExperimentVariantRepository(session)

    async def start_session_from_candidate_strategy_proposal(
        self, proposal_id: int, confirmed: bool, confirmed_by: str | None
    ) -> PaperSignalSession:
        """준비·준비승인된 제안에 대해 active 신호 세션을 만든다. 상태 전환/주문 없음."""
        if not confirmed:
            raise ConfirmationRequiredError("confirmed must be true")
        if not confirmed_by:
            raise ConfirmationRequiredError("confirmed_by is required")

        proposal = await self._proposal_repo.get(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(proposal_id)
        if proposal.status != "approved":
            raise ProposalNotApprovedError(
                f"proposal {proposal_id} is {proposal.status!r}, not approved"
            )
        if proposal.experiment_id is None:
            raise NotPreparedError(
                f"proposal {proposal_id} has no prepared experiment — prepare first"
            )
        if not (proposal.suggested_parameters or {}).get(_READY_AT_KEY):
            raise NotReadyError(
                f"proposal {proposal_id} has no paper-readiness approval — approve readiness first"
            )

        # 연결된 전략 버전을 찾는다(experiment variants 경유).
        variants = await self._variant_repo.list_by_experiment(proposal.experiment_id)
        versions = []
        for va in variants:
            v = await self._version_repo.get(va.strategy_version_id)
            if v is not None:
                versions.append(v)
        if not versions:
            raise InvalidVersionStateError(
                f"experiment {proposal.experiment_id} has no strategy version"
            )
        # 모든 버전은 DRAFT여야 하고 자동매매 토글이 꺼져 있어야 한다.
        for v in versions:
            if v.status != StrategyVersionStatus.DRAFT:
                raise InvalidVersionStateError(
                    f"strategy_version {v.id} is {v.status.value}, not draft"
                )
            if (v.parameters or {}).get("auto_trade_enabled"):
                raise UnexpectedAutoTradeError(
                    f"strategy_version {v.id} has auto-trade enabled — refusing to start"
                )

        # 같은 제안에 이미 active 세션이 있으면 거부(중복 방지).
        existing = await self._repo.find_active_for_proposal(proposal_id)
        if existing is not None:
            raise DuplicateActiveSessionError(
                f"proposal {proposal_id} already has an active session ({existing.id})"
            )

        version = versions[0]
        session_row = await self._repo.create(
            candidate_strategy_proposal_id=proposal.id,
            experiment_id=proposal.experiment_id,
            strategy_version_id=version.id,
            candidate_event_id=proposal.candidate_event_id,
            symbol_code=proposal.symbol_code,
            status="active",
            started_by=confirmed_by,
        )
        await self._session.commit()
        return session_row

    async def stop_session(
        self, session_id: int, confirmed_by: str | None, note: str | None = None
    ) -> PaperSignalSession:
        """active 세션을 stopped로 표시한다. 이후 run에서 신호가 더 쌓이지 않는다."""
        if not confirmed_by:
            raise ConfirmationRequiredError("confirmed_by is required")
        session_row = await self._repo.get(session_id)
        if session_row is None:
            raise SessionNotFoundError(session_id)
        if session_row.status == "stopped":
            return session_row  # idempotent
        session_row = await self._repo.update(
            session_row,
            status="stopped",
            stopped_at=datetime.now(timezone.utc),
            stopped_by=confirmed_by,
            note=note,
        )
        await self._session.commit()
        return session_row

    async def list_sessions(
        self, status: str | None = None, limit: int = 200, offset: int = 0
    ) -> list[PaperSignalSession]:
        return await self._repo.list_filtered(status=status, limit=limit, offset=offset)

    async def run_due_sessions(self, now: datetime | None = None) -> RunSummary:
        """active 세션마다 DRAFT 전략 버전으로 SignalLog만 생성한다. 주문/체결/Trade 없음.

        signal_service가 없으면(잘못된 구성) 아무것도 하지 않는다.
        """
        if self._signal_service is None:
            return RunSummary(checked=0, signals_created=0, skipped=0, errors=["no signal_service"])

        sessions = await self._repo.list_active()
        signals_created = 0
        skipped = 0
        errors: list[str] = []
        run_at = now or datetime.now(timezone.utc)

        for s in sessions:
            if s.strategy_version_id is None:
                skipped += 1
                await self._repo.update(s, last_run_at=run_at, last_error="version missing")
                continue
            version = await self._version_repo.get(s.strategy_version_id)
            # 방어적: 버전이 사라졌거나 DRAFT가 아니면(=다른 경로가 관리 중) 신호 세션은 건너뛴다.
            if version is None or version.status != StrategyVersionStatus.DRAFT:
                skipped += 1
                await self._repo.update(
                    s, last_run_at=run_at, last_error="version not draft — skipped"
                )
                continue
            params = version.parameters or {}
            if params.get("auto_trade_enabled"):
                skipped += 1
                await self._repo.update(
                    s, last_run_at=run_at, last_error="auto-trade enabled — skipped"
                )
                continue
            strategy = create_strategy(params.get("strategy_type", ""), params)
            if strategy is None:
                skipped += 1
                await self._repo.update(s, last_run_at=run_at, last_error="unknown strategy_type")
                continue
            try:
                # signal-only: SignalLog만 기록한다. TradeService/주문 경로 없음.
                log = await self._signal_service.generate_and_log_signal(
                    strategy,
                    s.symbol_code,
                    version.id,
                    strategy_params=params,
                    market=params.get("market", "KR"),
                    exchange=params.get("exchange"),
                )
            except Exception as exc:  # noqa: BLE001 - 한 세션 실패가 잡을 중단하지 않도록
                errors.append(f"session {s.id}: {exc}")
                await self._repo.update(s, last_run_at=run_at, last_error=str(exc))
                continue
            created = log is not None
            if created:
                signals_created += 1
            await self._repo.update(
                s,
                last_run_at=run_at,
                last_error=None,
                run_count=s.run_count + 1,
                signal_count=s.signal_count + (1 if created else 0),
            )

        await self._session.commit()
        return RunSummary(
            checked=len(sessions), signals_created=signals_created, skipped=skipped, errors=errors
        )
