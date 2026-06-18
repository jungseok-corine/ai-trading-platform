"""C-2.12: Trading Guard API.

자동매매 pause/resume 상태를 조회하고 수동으로 제어하는 엔드포인트.

보안 제약:
  - AI 분석 결과가 이 엔드포인트를 호출해 resume해서는 안 된다.
  - resume은 사람이 명시적으로 API를 통해서만 수행한다.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.trading_guard_service import TradingGuardService
from app.trading.strategy.schemas import PauseRequest, ResumeRequest, TradingGuardStateRead

router = APIRouter(tags=["trading-guard"])


def _to_read(state, account_id: int) -> TradingGuardStateRead:
    if state is None:
        return TradingGuardStateRead(account_id=account_id, is_paused=False)
    return TradingGuardStateRead(
        account_id=state.account_id,
        is_paused=state.is_paused,
        pause_reason=state.pause_reason,
        pause_source=state.pause_source,
        paused_at=state.paused_at,
        paused_by=state.paused_by,
        resolved_at=state.resolved_at,
        resolved_by=state.resolved_by,
        resolution_note=state.resolution_note,
        related_risk_event_id=state.related_risk_event_id,
        updated_at=state.updated_at,
    )


@router.get("/accounts/{account_id}/trading-guard/status", response_model=TradingGuardStateRead)
async def get_trading_guard_status(
    account_id: int,
    session: AsyncSession = Depends(get_db),
) -> TradingGuardStateRead:
    svc = TradingGuardService(session)
    state = await svc.get_state(account_id)
    return _to_read(state, account_id)


@router.post("/accounts/{account_id}/trading-guard/pause", response_model=TradingGuardStateRead)
async def pause_trading(
    account_id: int,
    body: PauseRequest,
    session: AsyncSession = Depends(get_db),
) -> TradingGuardStateRead:
    svc = TradingGuardService(session)
    state = await svc.manual_pause(account_id=account_id, reason=body.reason)
    return _to_read(state, account_id)


@router.post("/accounts/{account_id}/trading-guard/resume", response_model=TradingGuardStateRead)
async def resume_trading(
    account_id: int,
    body: ResumeRequest,
    session: AsyncSession = Depends(get_db),
) -> TradingGuardStateRead:
    """자동매매를 재개한다.

    반드시 사람이 명시적으로 호출해야 한다. AI 분석 코드가 이 엔드포인트를 자동
    호출하는 것은 금지된다.
    """
    svc = TradingGuardService(session)
    state = await svc.get_state(account_id)
    if state is None or not state.is_paused:
        raise HTTPException(status_code=400, detail="Account is not currently paused.")
    state = await svc.resume(
        account_id=account_id,
        resolved_by="user",
        resolution_note=body.resolution_note,
    )
    return _to_read(state, account_id)
