from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker_client
from app.db.session import get_db
from app.domain.models.risk import RiskConfig
from app.services.risk_service import RiskConfigNotFoundError, RiskService
from app.trading.broker.base import BrokerClient
from app.trading.risk.schemas import EmergencyStopRequest, RiskConfigRead, RiskConfigUpdate

router = APIRouter(prefix="/risk-config", tags=["risk-config"])


def get_risk_service(
    session: AsyncSession = Depends(get_db),
    broker: BrokerClient = Depends(get_broker_client),
) -> RiskService:
    return RiskService(session, broker)


@router.get("/{account_id}", response_model=RiskConfigRead)
async def get_risk_config(
    account_id: int, service: RiskService = Depends(get_risk_service)
) -> RiskConfig:
    try:
        return await service.get_config(account_id)
    except RiskConfigNotFoundError as e:
        raise HTTPException(status_code=404, detail="risk config not found") from e


@router.patch("/{account_id}", response_model=RiskConfigRead)
async def update_risk_config(
    account_id: int,
    payload: RiskConfigUpdate,
    service: RiskService = Depends(get_risk_service),
) -> RiskConfig:
    try:
        return await service.update_config(account_id, **payload.model_dump(exclude_unset=True))
    except RiskConfigNotFoundError as e:
        raise HTTPException(status_code=404, detail="risk config not found") from e


@router.post("/{account_id}/emergency-stop", response_model=RiskConfigRead)
async def set_emergency_stop(
    account_id: int,
    payload: EmergencyStopRequest,
    service: RiskService = Depends(get_risk_service),
) -> RiskConfig:
    try:
        return await service.set_emergency_stop(account_id, payload.enabled)
    except RiskConfigNotFoundError as e:
        raise HTTPException(status_code=404, detail="risk config not found") from e
