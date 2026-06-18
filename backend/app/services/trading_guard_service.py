"""C-2.12: 자동매매 Auto-Pause Safety Gate.

real mode에서 position mismatch 등 정합성 문제가 탐지되면 자동으로 pause 상태로
전환하고, 사람이 수동으로 resume하기 전까지 신규 주문을 차단한다.

paper mode는 자동 보정 + warning만 적용하며 auto-pause 대상이 아니다.

방어 레이어:
  1. StrategyRunnerService._attempt_auto_trade() — early abort (execute_signal 호출 전)
  2. TradeService.execute_signal() — final block (broker.place_order 호출 전)
  3. RiskConfig.emergency_stop=True — EmergencyStopRule 경유 기존 차단 (방어적 중복)
"""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import PauseSource
from app.domain.models.trading_guard import TradingGuardState
from app.domain.repositories.risk import RiskConfigRepository
from app.domain.repositories.trading_guard import TradingGuardRepository

logger = logging.getLogger(__name__)
_KST = ZoneInfo("Asia/Seoul")


class TradingGuardService:
    """TradingGuardState 조회/변경 및 emergency_stop 연동을 담당한다."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = TradingGuardRepository(session)
        self._risk_config_repo = RiskConfigRepository(session)

    async def get_state(self, account_id: int) -> TradingGuardState | None:
        return await self._repo.get_by_account_id(account_id)

    async def is_paused(self, account_id: int) -> bool:
        state = await self._repo.get_by_account_id(account_id)
        return state is not None and state.is_paused

    async def auto_pause(
        self,
        account_id: int,
        reason: str,
        source: PauseSource,
        risk_event_id: int | None = None,
    ) -> TradingGuardState:
        """시스템이 자동으로 pause 상태로 전환한다.

        이미 pause 상태이면 reason/source를 최신 정보로 갱신하고 paused_at은 유지한다.
        """
        state = await self._repo.get_by_account_id(account_id)
        now = datetime.now(_KST)

        if state is None:
            state = await self._repo.create(
                account_id=account_id,
                is_paused=True,
                pause_reason=reason,
                pause_source=source,
                paused_at=now,
                paused_by="system",
                related_risk_event_id=risk_event_id,
            )
        else:
            updates: dict = {
                "is_paused": True,
                "pause_reason": reason,
                "pause_source": source,
                "paused_by": "system",
                "related_risk_event_id": risk_event_id,
            }
            if not state.is_paused:
                updates["paused_at"] = now
                updates["resolved_at"] = None
                updates["resolved_by"] = None
                updates["resolution_note"] = None
            state = await self._repo.update(state, **updates)

        await self._set_emergency_stop(account_id, True)
        await self._session.commit()
        logger.warning(
            "trading guard: auto-pause activated account=%d source=%s reason=%s",
            account_id, source.value, reason,
        )
        return state

    async def manual_pause(
        self,
        account_id: int,
        reason: str,
        paused_by: str = "user",
    ) -> TradingGuardState:
        """사용자가 수동으로 pause 상태로 전환한다."""
        state = await self._repo.get_by_account_id(account_id)
        now = datetime.now(_KST)

        if state is None:
            state = await self._repo.create(
                account_id=account_id,
                is_paused=True,
                pause_reason=reason,
                pause_source=PauseSource.MANUAL,
                paused_at=now,
                paused_by=paused_by,
            )
        else:
            state = await self._repo.update(
                state,
                is_paused=True,
                pause_reason=reason,
                pause_source=PauseSource.MANUAL,
                paused_at=now,
                paused_by=paused_by,
                resolved_at=None,
                resolved_by=None,
                resolution_note=None,
            )

        await self._set_emergency_stop(account_id, True)
        await self._session.commit()
        logger.info("trading guard: manual pause account=%d by=%s", account_id, paused_by)
        return state

    async def resume(
        self,
        account_id: int,
        resolved_by: str,
        resolution_note: str | None = None,
    ) -> TradingGuardState:
        """사람이 수동으로 pause를 해제한다.

        AI 분석 결과가 이 함수를 호출하면 안 된다. 반드시 사람이 명시적으로 API를 통해 호출해야 한다.
        """
        state = await self._repo.get_by_account_id(account_id)
        now = datetime.now(_KST)

        if state is None:
            state = await self._repo.create(
                account_id=account_id,
                is_paused=False,
                resolved_at=now,
                resolved_by=resolved_by,
                resolution_note=resolution_note,
            )
        else:
            state = await self._repo.update(
                state,
                is_paused=False,
                resolved_at=now,
                resolved_by=resolved_by,
                resolution_note=resolution_note,
            )

        await self._set_emergency_stop(account_id, False)
        await self._session.commit()
        logger.info(
            "trading guard: resumed account=%d by=%s note=%s",
            account_id, resolved_by, resolution_note,
        )
        return state

    async def _set_emergency_stop(self, account_id: int, enabled: bool) -> None:
        """defense-in-depth: risk_config가 있으면 emergency_stop도 함께 전환한다."""
        try:
            config = await self._risk_config_repo.get_by_account_id(account_id)
            if config is not None:
                await self._risk_config_repo.update(config, emergency_stop=enabled)
        except Exception:  # noqa: BLE001
            logger.warning(
                "trading guard: failed to sync emergency_stop for account=%d", account_id
            )
