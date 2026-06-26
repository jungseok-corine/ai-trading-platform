"""Paper Signal Session Comparison (read-only) — M2.1.

두 개의 기존 PaperSignalSession을 신호 outcome 지표로 나란히 비교한다.
이것은 **순수 읽기 전용 측정**이다 (M2 설계 §3 Option E):

- 각 세션에 대해 기존 PaperSignalOutcomeService.session_outcomes를 재사용한다
  (SignalLog + market_data만 읽음 — SignalOutcomeService 경유).
- StrategyVersion/Experiment/PaperSignalSession 상태를 **바꾸지 않는다**.
- challenger 버전/세션/실험/제안을 **만들지 않는다**. ProposalService.approve 미호출.
- Trade/Order/AssignmentLog/SignalLog를 만들지 않는다. 스케줄러 잡을 켜지 않는다.
- 매수/매도 추천을 하지 않고, 통계적 유의성을 주장하지 않는다 (경고만 표시).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.paper_signal_session import PaperSignalSessionRepository
from app.services.paper_signal_outcome_service import (
    InvalidHorizonError,
    PaperSignalOutcomeService,
    SessionNotFoundError,
    SessionOutcomeBoard,
)
from app.services.signal_outcome_service import HORIZONS

# 분석된 신호 수가 이보다 적으면 통계적으로 의미 없다는 경고를 단다.
MIN_ANALYZED_FOR_MEANINGFUL = 5


class SameSessionError(Exception):
    """baseline과 challenger가 같은 세션일 때."""


def _delta(challenger: float | int | None, baseline: float | int | None) -> float | None:
    """challenger - baseline. 둘 중 하나라도 None이면 None(델타 계산 불가)."""
    if challenger is None or baseline is None:
        return None
    return round(challenger - baseline, 4)


def _side_summary(board: SessionOutcomeBoard, strategy_version_id: int | None) -> dict:
    """비교 응답에 넣을 한쪽(세션) 요약. board(outcome)에 version_id를 더한다."""
    return {
        "session_id": board.session_id,
        "status": board.status,
        "symbol_code": board.symbol_code,
        "strategy_version_id": strategy_version_id,
        "signal_count": board.signal_count,
        "analyzed_count": board.analyzed_count,
        "pending_count": board.pending_count,
        "win_rate": board.win_rate,
        "avg_return_pct": board.avg_return_pct,
        "best_return_pct": board.best_return_pct,
        "worst_return_pct": board.worst_return_pct,
        "by_action": [b.__dict__ for b in board.by_action],
    }


def _by_action_deltas(
    baseline: SessionOutcomeBoard, challenger: SessionOutcomeBoard
) -> list[dict]:
    """action별(buy/sell) 델타. 양쪽 어디든 등장한 action을 합쳐 계산."""
    base = {b.action: b for b in baseline.by_action}
    chal = {b.action: b for b in challenger.by_action}
    rows: list[dict] = []
    for action in sorted(set(base) | set(chal)):
        b = base.get(action)
        c = chal.get(action)
        rows.append({
            "action": action,
            "count_delta": _delta(
                c.count if c else 0, b.count if b else 0
            ),
            "analyzed_count_delta": _delta(
                c.analyzed_count if c else 0, b.analyzed_count if b else 0
            ),
            "win_rate_delta": _delta(
                c.win_rate if c else None, b.win_rate if b else None
            ),
            "avg_return_pct_delta": _delta(
                c.avg_return_pct if c else None, b.avg_return_pct if b else None
            ),
        })
    return rows


@dataclass
class PaperSignalComparison:
    baseline_session_id: int
    challenger_session_id: int
    horizon_minutes: int
    generated_at: str
    symbol_match: bool
    baseline: dict
    challenger: dict
    deltas: dict
    warnings: list[str]

    def to_dict(self) -> dict:
        return {
            "baseline_session_id": self.baseline_session_id,
            "challenger_session_id": self.challenger_session_id,
            "horizon_minutes": self.horizon_minutes,
            "generated_at": self.generated_at,
            "symbol_match": self.symbol_match,
            "baseline": self.baseline,
            "challenger": self.challenger,
            "deltas": self.deltas,
            "warnings": self.warnings,
        }


class PaperSignalComparisonService:
    """두 PaperSignalSession의 신호 outcome을 읽기 전용으로 비교한다."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._session_repo = PaperSignalSessionRepository(session)
        self._outcome_service = PaperSignalOutcomeService(session)

    async def compare(
        self,
        baseline_session_id: int,
        challenger_session_id: int,
        horizon_minutes: int = 30,
    ) -> PaperSignalComparison:
        # 1) horizon 검증(가장 싼 검증 먼저). session_outcomes도 동일 검증을 하지만 명시한다.
        if horizon_minutes not in HORIZONS:
            raise InvalidHorizonError(
                f"horizon_minutes must be one of {HORIZONS}, got {horizon_minutes}"
            )
        # 2) 같은 세션 비교 거부.
        if baseline_session_id == challenger_session_id:
            raise SameSessionError(
                "baseline and challenger session ids must differ"
            )

        # 3) 각 세션의 outcome 계산(읽기 전용). 없으면 SessionNotFoundError → 404.
        baseline_board = await self._outcome_service.session_outcomes(
            baseline_session_id, horizon_minutes=horizon_minutes
        )
        challenger_board = await self._outcome_service.session_outcomes(
            challenger_session_id, horizon_minutes=horizon_minutes
        )

        # 4) strategy_version_id는 outcome board에 없으므로 세션 레코드에서 읽는다.
        baseline_sess = await self._session_repo.get(baseline_session_id)
        challenger_sess = await self._session_repo.get(challenger_session_id)
        baseline_version = baseline_sess.strategy_version_id if baseline_sess else None
        challenger_version = (
            challenger_sess.strategy_version_id if challenger_sess else None
        )

        symbol_match = baseline_board.symbol_code == challenger_board.symbol_code

        deltas = {
            "signal_count_delta": _delta(
                challenger_board.signal_count, baseline_board.signal_count
            ),
            "analyzed_count_delta": _delta(
                challenger_board.analyzed_count, baseline_board.analyzed_count
            ),
            "pending_count_delta": _delta(
                challenger_board.pending_count, baseline_board.pending_count
            ),
            "win_rate_delta": _delta(
                challenger_board.win_rate, baseline_board.win_rate
            ),
            "avg_return_pct_delta": _delta(
                challenger_board.avg_return_pct, baseline_board.avg_return_pct
            ),
            "best_return_pct_delta": _delta(
                challenger_board.best_return_pct, baseline_board.best_return_pct
            ),
            "worst_return_pct_delta": _delta(
                challenger_board.worst_return_pct, baseline_board.worst_return_pct
            ),
            "by_action": _by_action_deltas(baseline_board, challenger_board),
        }

        warnings: list[str] = []
        if not symbol_match:
            warnings.append(
                "Compared sessions have different symbols; interpretation may be limited."
            )
        if (
            baseline_board.analyzed_count < MIN_ANALYZED_FOR_MEANINGFUL
            or challenger_board.analyzed_count < MIN_ANALYZED_FOR_MEANINGFUL
        ):
            warnings.append(
                "Low analyzed signal count; comparison is not statistically meaningful."
            )

        return PaperSignalComparison(
            baseline_session_id=baseline_session_id,
            challenger_session_id=challenger_session_id,
            horizon_minutes=horizon_minutes,
            generated_at=datetime.now(timezone.utc).isoformat(),
            symbol_match=symbol_match,
            baseline=_side_summary(baseline_board, baseline_version),
            challenger=_side_summary(challenger_board, challenger_version),
            deltas=deltas,
            warnings=warnings,
        )


__all__ = [
    "PaperSignalComparison",
    "PaperSignalComparisonService",
    "SameSessionError",
    "SessionNotFoundError",
    "InvalidHorizonError",
]
