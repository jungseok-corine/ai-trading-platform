from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.risk import RiskConfig
from app.domain.models.strategy import StrategyVersion
from app.domain.models.trading_guard import TradingGuardState

# 운영자가 한눈에 봐야 할 자동매매/실거래 관련 스케줄러 잡들.
_TRADING_SCHEDULER_KEYS = (
    "strategy_scheduler_enabled",
    "order_sync_scheduler_enabled",
    "trading_state_sync_scheduler_enabled",
)


class SafetyStatusService:
    """안전 불변식 '점검 패널' (C-3.3).

    프로젝트의 핵심 안전 불변식(실거래 비활성, 자동매매 off, 가드/비상정지)이 어디선가
    슬그머니 바뀌지 않았는지를 한 화면에서 확인한다. read-only 점검 — 아무것도 바꾸지
    않으며, 드리프트가 보이면 경고 문자열로만 알린다(해제/변경은 사람이 별도로).

    핵심 불변식:
      - KIS_REAL_TRADING_ENABLED=false
      - 활성/테스트 전략 버전의 auto_trade_enabled가 모두 false
      - (참고) 가드 pause/비상정지 상태는 표시만(이건 안전 방향이므로 경고 아님)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def status(self) -> dict:
        settings = get_settings()
        real_trading_enabled = bool(settings.kis_real_trading_enabled)

        auto_trade_versions = await self._auto_trade_versions()
        paused, guard_total = await self._guard_counts()
        emergency_stops, risk_total = await self._emergency_counts()

        schedulers = {k: bool(getattr(settings, k, False)) for k in _TRADING_SCHEDULER_KEYS}

        warnings: list[str] = []
        if real_trading_enabled:
            warnings.append("KIS_REAL_TRADING_ENABLED=true — 실거래가 켜져 있습니다.")
        if auto_trade_versions:
            warnings.append(
                f"auto_trade_enabled 전략 버전 {auto_trade_versions}개 (활성/테스트) — 확인 필요."
            )

        # 핵심 불변식: 실거래 off + 자동매매 버전 0. (가드 pause/비상정지는 안전 방향이라 제외)
        invariants_ok = (not real_trading_enabled) and auto_trade_versions == 0

        return {
            "invariants_ok": invariants_ok,
            "real_trading_enabled": real_trading_enabled,
            "auto_trade_versions": auto_trade_versions,
            "guards": {"total": guard_total, "paused": paused},
            "risk": {"configs": risk_total, "emergency_stops": emergency_stops},
            "schedulers": schedulers,
            "warnings": warnings,
        }

    async def _auto_trade_versions(self) -> int:
        """활성/테스트 버전 중 자동매매(단일종목 auto_trade_enabled + 유니버스 universe_auto_trade) 개수."""
        from app.trading.strategy.schemas import params_auto_trades

        rows = (
            await self._session.execute(
                select(StrategyVersion.parameters).where(
                    StrategyVersion.status.in_(
                        [StrategyVersionStatus.ACTIVE, StrategyVersionStatus.TESTING]
                    )
                )
            )
        ).scalars().all()
        return sum(1 for p in rows if isinstance(p, dict) and params_auto_trades(p))

    async def _guard_counts(self) -> tuple[int, int]:
        total = (
            await self._session.execute(select(func.count(TradingGuardState.id)))
        ).scalar() or 0
        paused = (
            await self._session.execute(
                select(func.count(TradingGuardState.id)).where(
                    TradingGuardState.is_paused.is_(True)
                )
            )
        ).scalar() or 0
        return paused, total

    async def _emergency_counts(self) -> tuple[int, int]:
        total = (
            await self._session.execute(select(func.count(RiskConfig.id)))
        ).scalar() or 0
        stops = (
            await self._session.execute(
                select(func.count(RiskConfig.id)).where(RiskConfig.emergency_stop.is_(True))
            )
        ).scalar() or 0
        return stops, total
