"""Paper Signal Session → AI 분석 입력(payload) 빌더 (read-only).

PaperSignalSession 기준으로 LLM에 바로 넘길 수 있는 structured 분석 입력을 만든다.
**실제 AI API 호출 없음, DB 쓰기 없음.** 분석 재료(input)만 결정론적으로 패키징한다.

설계 원칙:
- PaperSignalOutcomeService 재사용(신호 outcome 계산 중복 없음).
- 후보→제안→준비→세션의 추적 정보를 한 payload에 모은다.
- recent_signals 등은 상한(bounded)으로 잘라 거대한 JSON 덤프를 피한다.
- AiAnalysisRun/AiModelResponse 생성 없음, 전략/실험/세션/제안 변경 없음.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.repositories.candidate_event import CandidateEventRepository
from app.domain.repositories.candidate_strategy_proposal import (
    CandidateStrategyProposalRepository,
)
from app.domain.repositories.experiment import ExperimentRepository
from app.domain.repositories.paper_signal_session import PaperSignalSessionRepository
from app.domain.repositories.strategy import StrategyVersionRepository
from app.domain.repositories.trade import TradeRepository
from app.services.paper_signal_outcome_service import (
    InvalidHorizonError,
    PaperSignalOutcomeService,
    SessionNotFoundError,
)

# recent_signals 상한 (거대한 payload 방지). outcome 보드(20)보다 보수적.
_RECENT_SIGNAL_LIMIT = 10

_LIMITATIONS: list[str] = [
    "Signal outcome is hypothetical next-candle entry; no order/fill is involved.",
    "This is a paper SIGNAL-ONLY session: no trades, no orders, no broker calls.",
    "The linked StrategyVersion stays DRAFT and is invisible to the trade-capable runner.",
    "auto_trade_enabled is false and real trading is disabled.",
    "This payload is analysis input only — not financial advice, no action is taken.",
]


@dataclass
class PaperSignalAnalysisInput:
    generated_at: str
    horizon_minutes: int
    session: dict
    candidate_proposal: dict
    experiment_version: dict
    outcome_summary: dict
    safety: dict
    limitations: list[str]

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "horizon_minutes": self.horizon_minutes,
            "session": self.session,
            "candidate_proposal": self.candidate_proposal,
            "experiment_version": self.experiment_version,
            "outcome_summary": self.outcome_summary,
            "safety": self.safety,
            "limitations": self.limitations,
        }


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


class PaperSignalAnalysisInputService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._session_repo = PaperSignalSessionRepository(session)
        self._proposal_repo = CandidateStrategyProposalRepository(session)
        self._candidate_repo = CandidateEventRepository(session)
        self._experiment_repo = ExperimentRepository(session)
        self._version_repo = StrategyVersionRepository(session)
        self._trade_repo = TradeRepository(session)
        self._outcome_service = PaperSignalOutcomeService(session)

    async def build_input(
        self, session_id: int, horizon_minutes: int = 30
    ) -> PaperSignalAnalysisInput:
        sess = await self._session_repo.get(session_id)
        if sess is None:
            raise SessionNotFoundError(session_id)

        # outcome 보드(읽기 전용) — horizon 검증 포함(InvalidHorizonError).
        board = await self._outcome_service.session_outcomes(
            session_id, horizon_minutes=horizon_minutes, recent_limit=_RECENT_SIGNAL_LIMIT
        )
        outcome = board.to_dict()

        # --- A. 세션 메타 ---
        session_meta = {
            "paper_signal_session_id": sess.id,
            "status": sess.status,
            "symbol_code": sess.symbol_code,
            "started_by": sess.started_by,
            "started_at": _iso(sess.started_at),
            "stopped_at": _iso(sess.stopped_at),
            "stopped_by": sess.stopped_by,
            "last_run_at": _iso(sess.last_run_at),
            "last_error": sess.last_error,
            "run_count": sess.run_count,
            "signal_count": sess.signal_count,
        }

        # --- B. 후보/제안 추적 ---
        proposal = await self._proposal_repo.get(sess.candidate_strategy_proposal_id)
        candidate = None
        cp: dict = {"candidate_strategy_proposal_id": sess.candidate_strategy_proposal_id}
        if proposal is not None:
            params = proposal.suggested_parameters or {}
            cp.update({
                "candidate_event_id": proposal.candidate_event_id,
                "symbol_code": proposal.symbol_code,
                "suggested_strategy_type": proposal.suggested_strategy_type,
                "rationale": proposal.rationale,
                "confidence": proposal.confidence,
                "proposal_status": proposal.status,
                "prepared_experiment_id": proposal.experiment_id,
                "prepared_at": _iso(proposal.prepared_at),
                "readiness_approved_at": params.get("_paper_testing_ready_at"),
                "readiness_approved_by": params.get("_paper_testing_ready_by"),
            })
            candidate = await self._candidate_repo.get(proposal.candidate_event_id)
        if candidate is not None:
            cp.update({
                "candidate_score": candidate.score,
                "matched_conditions": candidate.matched_conditions,
                "candidate_facts": candidate.facts,
                "candidate_market": candidate.market.value,
            })

        # --- C. 실험/버전 상태 ---
        ev: dict = {"experiment_id": sess.experiment_id, "strategy_version_id": sess.strategy_version_id}
        if sess.experiment_id is not None:
            experiment = await self._experiment_repo.get(sess.experiment_id)
            ev["experiment_status"] = experiment.status.value if experiment else None
        trades_count = 0
        if sess.strategy_version_id is not None:
            version = await self._version_repo.get(sess.strategy_version_id)
            if version is not None:
                ev["strategy_version_status"] = version.status.value
                ev["auto_trade_enabled"] = bool((version.parameters or {}).get("auto_trade_enabled", False))
                trades_count = await self._trade_repo.count_by_strategy_version(version.id)
        ev["signal_only"] = True
        ev["trades_count_for_version"] = trades_count  # 항상 0이어야 함(주문 없음)

        # --- E. 안전 상태 ---
        settings = get_settings()
        safety = {
            "real_trading_enabled": settings.kis_real_trading_enabled,  # False
            "auto_trade_enabled": ev.get("auto_trade_enabled", False),
            "paper_signal_session_runner_enabled": settings.paper_signal_session_runner_enabled,
            "trades_count": trades_count,
            "note": "signal-only analysis — no orders, no live trading, no action taken",
        }

        return PaperSignalAnalysisInput(
            generated_at=datetime.now(timezone.utc).isoformat(),
            horizon_minutes=horizon_minutes,
            session=session_meta,
            candidate_proposal=cp,
            experiment_version=ev,
            outcome_summary=outcome,
            safety=safety,
            limitations=list(_LIMITATIONS),
        )


__all__ = [
    "PaperSignalAnalysisInputService",
    "PaperSignalAnalysisInput",
    "SessionNotFoundError",
    "InvalidHorizonError",
]
