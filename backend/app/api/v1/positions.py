from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker_client
from app.db.session import get_db
from app.domain.repositories.position import PositionRepository
from app.domain.repositories.position_event import PositionEventRepository
from app.services.portfolio_service import PortfolioService
from app.services.position_reconciliation_service import PositionReconciliationService
from app.services.position_service import PositionService
from app.services.trading_state_sync_service import TradingStateSyncService
from app.trading.broker.base import BrokerClient
from app.trading.position.schemas import (
    BrokerSyncResultRead,
    PortfolioSummaryRead,
    PositionEventRead,
    PositionRead,
    ReconciliationResultRead,
    RefreshPricesResultRead,
)
from app.trading.strategy.schemas import TradingStateSyncResultRead

router = APIRouter(tags=["positions"])


def get_position_service(
    session: AsyncSession = Depends(get_db),
    broker: BrokerClient = Depends(get_broker_client),
) -> PositionService:
    return PositionService(session, broker)


@router.get("/positions", response_model=list[PositionRead])
async def list_positions(
    account_id: int | None = None,
    include_closed: bool = Query(default=False),
    session: AsyncSession = Depends(get_db),
) -> list[PositionRead]:
    repo = PositionRepository(session)
    return await repo.list_by_account(account_id=account_id, include_closed=include_closed)


@router.post("/positions/refresh-prices", response_model=RefreshPricesResultRead)
async def refresh_all_position_prices(
    account_id: int,
    service: PositionService = Depends(get_position_service),
) -> RefreshPricesResultRead:
    positions = await service.refresh_all_prices(account_id)
    return RefreshPricesResultRead(updated=len(positions), positions=list(positions))


@router.post("/positions/sync-from-broker", response_model=BrokerSyncResultRead)
async def sync_positions_from_broker(
    account_id: int,
    service: PositionService = Depends(get_position_service),
) -> BrokerSyncResultRead:
    result = await service.sync_from_broker_positions(account_id)
    return BrokerSyncResultRead(
        created=result.created,
        updated=result.updated,
        zeroed=result.zeroed,
        positions=list(result.positions),
    )


@router.get("/portfolio/summary", response_model=PortfolioSummaryRead)
async def get_portfolio_summary(
    account_id: int,
    session: AsyncSession = Depends(get_db),
) -> PortfolioSummaryRead:
    return await PortfolioService(session).get_summary(account_id)


@router.post("/positions/{position_id}/refresh-price", response_model=PositionRead)
async def refresh_position_price(
    position_id: int,
    service: PositionService = Depends(get_position_service),
) -> PositionRead:
    position = await service.refresh_last_price(position_id)
    if position is None:
        raise HTTPException(status_code=404, detail="position not found")
    return position


@router.get("/positions/{position_id}/events", response_model=list[PositionEventRead])
async def list_position_events(
    position_id: int,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
) -> list[PositionEventRead]:
    repo = PositionEventRepository(session)
    return await repo.list_by_position(position_id, limit=limit, offset=offset)


@router.post("/accounts/{account_id}/positions/reconcile", response_model=ReconciliationResultRead)
async def reconcile_positions(
    account_id: int,
    session: AsyncSession = Depends(get_db),
    broker: BrokerClient = Depends(get_broker_client),
) -> ReconciliationResultRead:
    """브로커 잔고와 DB 포지션을 비교해 불일치를 탐지한다.

    paper 계좌: 불일치 발견 시 DB를 broker 기준으로 동기화한다.
    real 계좌: 불일치 발견 시 risk_event만 기록하고 DB는 수정하지 않는다.
    """
    svc = PositionReconciliationService(session, broker)
    result = await svc.reconcile(account_id)
    return ReconciliationResultRead.from_result(result)


@router.post("/accounts/{account_id}/trading-state/sync", response_model=TradingStateSyncResultRead)
async def sync_trading_state(
    account_id: int,
    session: AsyncSession = Depends(get_db),
    broker: BrokerClient = Depends(get_broker_client),
) -> TradingStateSyncResultRead:
    """pending 주문 체결 동기화 + 포지션 정합성 검사를 한 번에 실행한다 (수동 실행용).

    실행 순서:
    1. OrderSyncService: pending/partial 주문을 KIS 체결조회로 동기화 (VTTC0081R/TTTC0081R)
    2. PositionReconciliationService: 브로커 잔고와 DB 포지션 비교
       - paper 계좌: mismatch 시 DB 자동 보정
       - real 계좌: mismatch 시 risk_event 생성

    order sync 실패 시에도 reconciliation을 계속 시도하며, 결과의 warnings에 기록한다.
    """
    svc = TradingStateSyncService(session, broker)
    result = await svc.sync_account_trading_state(account_id)
    return TradingStateSyncResultRead(
        account_id=result.account_id,
        broker_mode=result.broker_mode,
        started_at=result.started_at,
        completed_at=result.completed_at,
        orders_checked=result.orders_checked,
        orders_updated=result.orders_updated,
        orders_cancelled=result.orders_cancelled,
        order_sync_errors=result.order_sync_errors,
        order_sync_error_category=result.order_sync_error_category,
        order_sync_skipped_reason=result.order_sync_skipped_reason,
        positions_compared=result.positions_compared,
        mismatches_count=result.mismatches_count,
        risk_events_created=result.risk_events_created,
        positions_synced_to_db=result.positions_synced_to_db,
        position_errors=result.position_errors,
        warnings=result.warnings,
    )


@router.get("/positions/{account_id}/{symbol_code}", response_model=PositionRead)
async def get_position(
    account_id: int,
    symbol_code: str,
    session: AsyncSession = Depends(get_db),
) -> PositionRead:
    repo = PositionRepository(session)
    position = await repo.get_by_account_symbol(account_id, symbol_code)
    if position is None:
        raise HTTPException(status_code=404, detail="position not found")
    return position
