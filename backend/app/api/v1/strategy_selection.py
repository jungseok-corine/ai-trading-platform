"""전략 종합 선정 보드 API (C-7.4). read-only — 실전 배치는 사람(승격 게이트)."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.strategy_selection_service import StrategySelectionService

router = APIRouter(prefix="/strategy-selection-board", tags=["strategy-selection"])


@router.get("")
async def get_selection_board(session: AsyncSession = Depends(get_db)) -> dict:
    return await StrategySelectionService(session).board()
