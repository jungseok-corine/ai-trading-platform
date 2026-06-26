"""Baseline ↔ Challenger Pair Run-Once (M2.10).

사람이 명시 확인하면 **명시한 baseline + challenger 두 active 세션만** 각각 1회씩 신호를 평가한다
(M2.9 Option B / D-23). 공정한 비교를 위해 한 요청에서 두 세션을 같은 시장 시점·같은 종목으로 샘플링한다.

핵심 안전 불변식:
- **명시한 두 세션만** 평가한다 — `list_active`/`run_due_sessions`/스케줄러 `run_now` 미사용.
- M2.8 단일 run-once의 **동일 검증/평가 코어**(`PaperSignalSessionRunOnceService.validate_session`/
  `evaluate_session`)를 재사용한다(검증 드리프트 방지). SignalLog만 생성(최대 2개, 세션당 0/1).
- 자격 실패(관계/심볼/버전 등)는 **실행 전 전체 거부(422)**. 런타임 skip(중복/장마감/무신호)은 정상 결과로
  계속한다(한쪽 성공·한쪽 skip = partial). 성공한 SignalLog를 다른쪽 skip 때문에 롤백하지 않는다.
- TradeService/OrderService/broker 주문 미구성. 세션/버전/제안/실험 status 무변경(카운터만). 잡 미활성.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.paper_signal_session import PaperSignalSessionRepository
from app.services.paper_signal_run_once_service import (
    PaperSignalSessionRunOnceService,
    RunOnceResult,
)


class PairBaselineNotFoundError(Exception):
    """baseline_id가 존재하지 않을 때 (404)."""


class PairChallengerNotFoundError(Exception):
    """challenger_id가 존재하지 않을 때 (404)."""


class NotChallengerSessionError(Exception):
    """challenger.source_type이 signal_challenger가 아닐 때 (422)."""


class BaselineMismatchError(Exception):
    """challenger.baseline_session_id가 제공된 baseline_id와 다를 때 (422)."""


class SymbolMismatchError(Exception):
    """baseline.symbol_code != challenger.symbol_code (422)."""


_PAIR_WARNINGS = [
    "This pair run creates SignalLogs only.",
    "No orders or trades are created.",
    "Recurring runner remains disabled.",
]


@dataclass
class PairRunOnceResult:
    baseline: RunOnceResult
    challenger: RunOnceResult
    orders_created: int = 0
    trades_created: int = 0
    runner_enabled: bool = False
    comparison_ready_hint: str = ""
    warnings: list[str] | None = None

    def to_dict(self) -> dict:
        def _side(r: RunOnceResult) -> dict:
            return {
                "session_id": r.session_id,
                "signal_created": r.signal_created,
                "signal_id": r.signal_id,
                "reason": r.reason,
            }

        return {
            "baseline": _side(self.baseline),
            "challenger": _side(self.challenger),
            "orders_created": self.orders_created,
            "trades_created": self.trades_created,
            "runner_enabled": self.runner_enabled,
            "comparison_ready_hint": self.comparison_ready_hint,
            "warnings": self.warnings or list(_PAIR_WARNINGS),
        }


class PaperSignalPairRunOnceService:
    """명시한 baseline + challenger 두 세션만 각각 1회 평가한다(SignalLog만)."""

    def __init__(self, session: AsyncSession, signal_service) -> None:
        self._session = session
        self._repo = PaperSignalSessionRepository(session)
        # 단일 run-once 서비스의 검증/평가 코어를 재사용(드리프트 방지). 커밋은 페어가 1회 한다.
        self._once = PaperSignalSessionRunOnceService(session, signal_service)

    async def run_pair(
        self,
        baseline_id: int,
        challenger_id: int,
        confirmed: bool,
        confirmed_by: str | None,
    ) -> PairRunOnceResult:
        # --- 게이트(실행 전 전체 검증) ---
        self._once.check_confirmation(confirmed, confirmed_by)
        self._once.check_global_gates()

        baseline = await self._repo.get(baseline_id)
        if baseline is None:
            raise PairBaselineNotFoundError(baseline_id)
        challenger = await self._repo.get(challenger_id)
        if challenger is None:
            raise PairChallengerNotFoundError(challenger_id)

        # 페어 관계 게이트 (422).
        if challenger.source_type != "signal_challenger":
            raise NotChallengerSessionError(
                f"challenger {challenger_id} source_type is {challenger.source_type!r}, "
                f"not signal_challenger"
            )
        if challenger.baseline_session_id != baseline_id:
            raise BaselineMismatchError(
                f"challenger {challenger_id} baseline_session_id "
                f"{challenger.baseline_session_id} != provided baseline {baseline_id}"
            )
        if baseline.symbol_code != challenger.symbol_code:
            raise SymbolMismatchError(
                f"symbol mismatch: baseline {baseline.symbol_code!r} != "
                f"challenger {challenger.symbol_code!r}"
            )

        # 두 세션 모두 **실행 전** 검증한다(한쪽이라도 실패하면 어느 쪽도 평가하지 않음).
        b_version, b_strategy = await self._once.validate_session(baseline)
        c_version, c_strategy = await self._once.validate_session(challenger)

        # --- 평가: baseline 먼저, challenger 다음. skip은 정상. 둘 다 한 트랜잭션에서 1회 커밋. ---
        b_result = await self._once.evaluate_session(baseline, b_version, b_strategy)
        c_result = await self._once.evaluate_session(challenger, c_version, c_strategy)
        await self._session.commit()

        both = b_result.signal_created and c_result.signal_created
        hint = (
            "both sides recorded a signal; re-run the comparison to see updated outcomes."
            if both
            else "pair evaluated; re-run the comparison (some sides may have skipped — "
            "dedupe/stale/no-signal). More signals accrue as you run again over time."
        )
        return PairRunOnceResult(
            baseline=b_result,
            challenger=c_result,
            orders_created=0,
            trades_created=0,
            runner_enabled=False,
            comparison_ready_hint=hint,
            warnings=list(_PAIR_WARNINGS),
        )


__all__ = [
    "PaperSignalPairRunOnceService",
    "PairRunOnceResult",
    "PairBaselineNotFoundError",
    "PairChallengerNotFoundError",
    "NotChallengerSessionError",
    "BaselineMismatchError",
    "SymbolMismatchError",
]
