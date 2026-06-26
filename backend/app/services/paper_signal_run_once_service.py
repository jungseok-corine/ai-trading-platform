"""Session-specific Paper Signal Run-Once (M2.8).

사람이 명시 확인하면 **선택한 단일 active PaperSignalSession**에 대해 신호를 **1회만** 평가한다.
M2.7 설계 Option B / D-22를 따른다.

핵심 안전 불변식:
- **선택한 1개 세션만** 평가한다 — `list_active()`/`run_due_sessions()`(전체 active)를 호출하지 않고,
  스케줄러 `run_now`도 쓰지 않는다.
- 기존 signal-only 경로(`SignalService.generate_and_log_signal`)만 호출한다 → **SignalLog만** 생성.
  TradeService/OrderService/broker 주문 미구성·미호출. broker는 캔들 시세 조회에만 쓰인다(SignalService 내부).
- 세션/버전/제안/실험 status를 바꾸지 않는다. 세션 운영 카운터(run_count/signal_count/last_run_at/
  last_error)만 갱신한다(기존 런너와 동일 의미). 스케줄러 잡을 켜지 않는다.
- dedupe/staleness는 SignalService가 처리한다(중복 캔들·장 마감 시 None 반환 → skipped).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models.enums import StrategyVersionStatus
from app.domain.repositories.paper_signal_session import PaperSignalSessionRepository
from app.domain.repositories.strategy import StrategyVersionRepository
from app.services.signal_service import SignalService
from app.trading.strategy.registry import create_strategy


class RunOnceSessionNotFoundError(Exception):
    """session_id가 존재하지 않을 때 (404)."""


class ConfirmationRequiredError(Exception):
    """confirmed/confirmed_by 누락 (422)."""


class SessionNotActiveError(Exception):
    """세션 status가 active가 아닐 때 (422)."""


class MissingVersionError(Exception):
    """strategy_version_id 누락 / 버전 없음 (422)."""


class VersionNotDraftError(Exception):
    """challenger 세션 버전이 DRAFT가 아닐 때 (422)."""


class VersionAutoTradeError(Exception):
    """버전 auto_trade_enabled=true (422) — 거부."""


class UnsupportedStrategyTypeError(Exception):
    """등록되지 않은 strategy_type (422)."""


class MissingSymbolError(Exception):
    """symbol_code 누락 (422)."""


class RealTradingEnabledError(Exception):
    """KIS_REAL_TRADING_ENABLED=true (422) — 거부."""


class RunnerEnabledError(Exception):
    """paper_signal_session_runner_enabled=true (422) — 동시 스케줄러 혼선 방지(V1)."""


@dataclass
class RunOnceResult:
    session_id: int
    status: str
    signal_created: bool
    signal_id: int | None = None
    reason: str | None = None
    orders_created: int = 0
    trades_created: int = 0
    runner_enabled: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "signal_created": self.signal_created,
            "signal_id": self.signal_id,
            "reason": self.reason,
            "orders_created": self.orders_created,
            "trades_created": self.trades_created,
            "runner_enabled": self.runner_enabled,
            "warnings": self.warnings,
        }


_BASE_WARNINGS = [
    "This run creates SignalLog only.",
    "No orders or trades are created.",
    "Recurring runner remains disabled.",
]


class PaperSignalSessionRunOnceService:
    """선택한 단일 active 세션에 대해 신호를 1회 평가한다(SignalLog만)."""

    def __init__(self, session: AsyncSession, signal_service: SignalService) -> None:
        self._session = session
        self._signal_service = signal_service
        self._repo = PaperSignalSessionRepository(session)
        self._version_repo = StrategyVersionRepository(session)

    async def run_once(
        self, session_id: int, confirmed: bool, confirmed_by: str | None
    ) -> RunOnceResult:
        if not confirmed:
            raise ConfirmationRequiredError("confirmed must be true")
        if not confirmed_by:
            raise ConfirmationRequiredError("confirmed_by is required")

        # 전역 안전 게이트: 실거래/상시 런너가 켜져 있으면 V1은 거부한다.
        settings = get_settings()
        if settings.kis_real_trading_enabled:
            raise RealTradingEnabledError("KIS_REAL_TRADING_ENABLED must be false")
        if settings.paper_signal_session_runner_enabled:
            raise RunnerEnabledError(
                "paper_signal_session_runner_enabled is true — refusing manual run-once "
                "to avoid concurrent scheduler runs (disable the recurring runner first)"
            )

        sess = await self._repo.get(session_id)
        if sess is None:
            raise RunOnceSessionNotFoundError(session_id)
        if sess.status != "active":
            raise SessionNotActiveError(
                f"session {session_id} status is {sess.status!r}, not active"
            )
        if sess.strategy_version_id is None:
            raise MissingVersionError(f"session {session_id} has no strategy_version_id")
        version = await self._version_repo.get(sess.strategy_version_id)
        if version is None:
            raise MissingVersionError(
                f"strategy_version {sess.strategy_version_id} not found"
            )
        # signal-only 트랙은 항상 DRAFT여야 한다(런너 비대상 보장). challenger/candidate 공통으로 강제.
        if version.status != StrategyVersionStatus.DRAFT:
            raise VersionNotDraftError(
                f"strategy_version {version.id} is {version.status.value}, not draft"
            )
        params = version.parameters or {}
        if params.get("auto_trade_enabled"):
            raise VersionAutoTradeError(
                f"strategy_version {version.id} has auto_trade_enabled=true — refusing run-once"
            )
        if not sess.symbol_code:
            raise MissingSymbolError(f"session {session_id} has no symbol_code")
        strategy = create_strategy(params.get("strategy_type", ""), params)
        if strategy is None:
            raise UnsupportedStrategyTypeError(
                f"strategy_type {params.get('strategy_type')!r} is not registered"
            )

        run_at = datetime.now(timezone.utc)
        warnings = list(_BASE_WARNINGS)

        # --- 단일 세션 평가: SignalLog만. 예외는 skipped로 흡수(크래시 아님) — 기존 런너 의미. ---
        try:
            log = await self._signal_service.generate_and_log_signal(
                strategy,
                sess.symbol_code,
                version.id,
                strategy_params=params,
                market=params.get("market", "KR"),
                exchange=params.get("exchange"),
            )
        except Exception as exc:  # noqa: BLE001 - 시세 오류 등은 skipped로 처리(런너와 동일)
            await self._repo.update(sess, last_run_at=run_at, last_error=str(exc))
            await self._session.commit()
            return RunOnceResult(
                session_id=sess.id, status=sess.status, signal_created=False,
                reason=f"signal evaluation error (treated as skipped): {exc}",
                runner_enabled=False, warnings=warnings,
            )

        created = log is not None
        signal_id: int | None = None
        reason: str | None = None
        if created:
            signal_id = log.id
            # 세션별 outcome 귀속(주문과 무관). 기존 런너와 동일.
            log.paper_signal_session_id = sess.id
        else:
            reason = (
                "no SignalLog created (no actionable strategy signal, stale/closed market, "
                "or duplicate candle)"
            )

        # 운영 카운터만 갱신 — 세션 status는 바꾸지 않는다(기존 런너 의미와 동일).
        await self._repo.update(
            sess,
            last_run_at=run_at,
            last_error=None,
            run_count=sess.run_count + 1,
            signal_count=sess.signal_count + (1 if created else 0),
        )
        await self._session.commit()

        return RunOnceResult(
            session_id=sess.id,
            status=sess.status,  # 불변: 'active'
            signal_created=created,
            signal_id=signal_id,
            reason=reason,
            orders_created=0,
            trades_created=0,
            runner_enabled=False,
            warnings=warnings,
        )


__all__ = [
    "PaperSignalSessionRunOnceService",
    "RunOnceResult",
    "RunOnceSessionNotFoundError",
    "ConfirmationRequiredError",
    "SessionNotActiveError",
    "MissingVersionError",
    "VersionNotDraftError",
    "VersionAutoTradeError",
    "UnsupportedStrategyTypeError",
    "MissingSymbolError",
    "RealTradingEnabledError",
    "RunnerEnabledError",
]
