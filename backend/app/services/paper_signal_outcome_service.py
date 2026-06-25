"""Paper Signal Session Outcome Board (read-only).

세션이 만든 SignalLog의 forward 수익률을 market_data로 계산해 세션 단위로 집계한다.
백테스트/주문/체결과 무관한 **읽기 전용 분석**이다:
- SignalLog + market_data만 읽는다(SignalOutcomeService 재사용).
- StrategyVersion/Experiment 상태를 바꾸지 않는다.
- Trade/Order/AssignmentLog를 만들지 않는다. 스케줄러 잡을 켜지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.paper_signal_session import PaperSignalSessionRepository
from app.domain.repositories.signal_log import SignalLogRepository
from app.services.signal_outcome_service import HORIZONS, SignalOutcomeService


class SessionNotFoundError(Exception):
    """paper_signal_session id가 존재하지 않을 때."""


class InvalidHorizonError(Exception):
    """지원하지 않는 horizon_minutes를 요청했을 때."""


@dataclass
class SessionSignalRow:
    signal_id: int
    created_at: str | None
    action: str  # buy | sell
    entry_price: float | None
    return_pct: float | None  # 신호 방향 기준(directional) — 양수=신호 방향 맞음
    is_win: bool | None
    outcome_status: str  # analyzed | pending


@dataclass
class ActionBreakdown:
    action: str
    count: int
    analyzed_count: int
    win_rate: float | None
    avg_return_pct: float | None


@dataclass
class SessionOutcomeBoard:
    session_id: int
    status: str
    symbol_code: str
    horizon_minutes: int
    signal_count: int
    analyzed_count: int
    pending_count: int
    win_rate: float | None
    avg_return_pct: float | None
    best_return_pct: float | None
    worst_return_pct: float | None
    by_action: list[ActionBreakdown]
    recent_signals: list[SessionSignalRow]

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "symbol_code": self.symbol_code,
            "horizon_minutes": self.horizon_minutes,
            "signal_count": self.signal_count,
            "analyzed_count": self.analyzed_count,
            "pending_count": self.pending_count,
            "win_rate": self.win_rate,
            "avg_return_pct": self.avg_return_pct,
            "best_return_pct": self.best_return_pct,
            "worst_return_pct": self.worst_return_pct,
            "by_action": [b.__dict__ for b in self.by_action],
            "recent_signals": [r.__dict__ for r in self.recent_signals],
        }


def _f(d: Decimal | None) -> float | None:
    return float(d) if d is not None else None


class PaperSignalOutcomeService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._session_repo = PaperSignalSessionRepository(session)
        self._signal_repo = SignalLogRepository(session)
        self._outcome_service = SignalOutcomeService(session)

    async def session_outcomes(
        self, session_id: int, horizon_minutes: int = 30, recent_limit: int = 20
    ) -> SessionOutcomeBoard:
        if horizon_minutes not in HORIZONS:
            raise InvalidHorizonError(
                f"horizon_minutes must be one of {HORIZONS}, got {horizon_minutes}"
            )
        sess = await self._session_repo.get(session_id)
        if sess is None:
            raise SessionNotFoundError(session_id)

        signals = await self._signal_repo.list_by_paper_signal_session(session_id)
        sig_by_id = {s.id: s for s in signals}
        outcomes = await self._outcome_service.compute_outcomes(signals)

        directional: list[float] = []
        wins = 0
        analyzed = 0
        by_action: dict[str, dict] = {}
        rows: list[SessionSignalRow] = []

        for o in outcomes:
            hr = next((h for h in o.horizons if h.horizon_minutes == horizon_minutes), None)
            available = bool(hr and hr.available and hr.return_pct is not None)
            action = o.signal_type.value
            agg = by_action.setdefault(action, {"count": 0, "analyzed": 0, "wins": 0, "rets": []})
            agg["count"] += 1
            dir_ret = _f(hr.directional_return_pct) if hr else None
            if available:
                analyzed += 1
                agg["analyzed"] += 1
                if dir_ret is not None:
                    directional.append(dir_ret)
                    agg["rets"].append(dir_ret)
                if hr.is_win:
                    wins += 1
                    agg["wins"] += 1
            sig = sig_by_id.get(o.signal_id)
            rows.append(SessionSignalRow(
                signal_id=o.signal_id,
                created_at=sig.generated_at.isoformat() if sig and sig.generated_at else None,
                action=action,
                entry_price=_f(o.entry_price),
                return_pct=dir_ret,
                is_win=hr.is_win if (hr and available) else None,
                outcome_status="analyzed" if available else "pending",
            ))

        signal_count = len(signals)
        win_rate = round(wins / analyzed * 100, 2) if analyzed else None
        avg_return = round(sum(directional) / len(directional), 4) if directional else None
        best = round(max(directional), 4) if directional else None
        worst = round(min(directional), 4) if directional else None

        action_rows: list[ActionBreakdown] = []
        for act, agg in sorted(by_action.items()):
            a_rets = agg["rets"]
            action_rows.append(ActionBreakdown(
                action=act,
                count=agg["count"],
                analyzed_count=agg["analyzed"],
                win_rate=round(agg["wins"] / agg["analyzed"] * 100, 2) if agg["analyzed"] else None,
                avg_return_pct=round(sum(a_rets) / len(a_rets), 4) if a_rets else None,
            ))

        # recent_signals: 최신순(이미 list_by_paper_signal_session가 desc) 상위 N
        recent = rows[:recent_limit]

        return SessionOutcomeBoard(
            session_id=sess.id,
            status=sess.status,
            symbol_code=sess.symbol_code,
            horizon_minutes=horizon_minutes,
            signal_count=signal_count,
            analyzed_count=analyzed,
            pending_count=signal_count - analyzed,
            win_rate=win_rate,
            avg_return_pct=avg_return,
            best_return_pct=best,
            worst_return_pct=worst,
            by_action=action_rows,
            recent_signals=recent,
        )
