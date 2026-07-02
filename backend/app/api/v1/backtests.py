"""백테스트 API (C-6.1).

저장된 market_data 위의 히스토리컬 리플레이. 주문/브로커/KIS 호출 없음 —
DB read + 순수 계산 + backtest_runs 기록만.
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.backtest_run import BacktestRun
from app.services.backtest_service import BacktestService

router = APIRouter(prefix="/backtests", tags=["backtests"])


def get_service(session: AsyncSession = Depends(get_db)) -> BacktestService:
    return BacktestService(session)


class BacktestRequest(BaseModel):
    strategy_type: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    symbol_code: str
    timeframe: str = "1m"
    start_ts: datetime
    end_ts: datetime
    market: str = "KR"
    initial_cash: int = Field(default=10_000_000, ge=10_000)
    lookback: int = Field(default=200, ge=30, le=1000)


def _to_read(run: BacktestRun, *, include_trades: bool) -> dict:
    body = {
        "id": run.id,
        "strategy_type": run.strategy_type,
        "parameters": run.parameters,
        "symbol_code": run.symbol_code,
        "timeframe": run.timeframe,
        "market": run.market,
        "start_ts": run.start_ts,
        "end_ts": run.end_ts,
        "status": run.status,
        "metrics": run.metrics,
        "error_message": run.error_message,
        "created_at": run.created_at,
    }
    if include_trades:
        body["simulated_trades"] = run.simulated_trades
    return body


@router.post("")
async def run_backtest(
    payload: BacktestRequest,
    service: BacktestService = Depends(get_service),
) -> dict:
    if payload.end_ts <= payload.start_ts:
        raise HTTPException(status_code=422, detail="end_ts는 start_ts 이후여야 합니다.")
    run = await service.run(
        strategy_type=payload.strategy_type,
        parameters=payload.parameters,
        symbol_code=payload.symbol_code,
        timeframe=payload.timeframe,
        start_ts=payload.start_ts,
        end_ts=payload.end_ts,
        market=payload.market,
        initial_cash=payload.initial_cash,
        lookback=payload.lookback,
    )
    return _to_read(run, include_trades=True)


@router.get("")
async def list_backtests(
    limit: int = Query(20, ge=1, le=100),
    service: BacktestService = Depends(get_service),
) -> list[dict]:
    runs = await service.list_recent(limit=limit)
    return [_to_read(r, include_trades=False) for r in runs]


@router.get("/{run_id}")
async def get_backtest(
    run_id: int,
    service: BacktestService = Depends(get_service),
) -> dict:
    run = await service.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"backtest run {run_id} 없음")
    return _to_read(run, include_trades=True)
