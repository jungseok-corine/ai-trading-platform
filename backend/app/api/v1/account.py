from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker_client
from app.db.session import get_db
from app.domain.repositories.account import AccountRepository
from app.services.manual_reconciliation_report_service import (
    ManualReconciliationReportService,
)
from app.services.paper_resume_readiness_service import (
    PaperResumeReadinessService,
)
from app.trading.broker.base import BrokerClient
from app.trading.broker.exceptions import KISAPIError
from app.trading.broker.schemas import AccountBalance

router = APIRouter(prefix="/account", tags=["account"])


@router.get("", response_model=AccountBalance)
async def get_account(
    broker: BrokerClient = Depends(get_broker_client),
) -> AccountBalance:
    try:
        return await broker.get_account_balance()
    except KISAPIError as e:
        raise HTTPException(status_code=502, detail=e.msg1) from e


class AccountRead(BaseModel):
    id: int
    account_type: str  # paper / live
    broker_account_no: str
    alias: str | None = None


@router.get("/list", response_model=list[AccountRead])
async def list_accounts(session: AsyncSession = Depends(get_db)) -> list[AccountRead]:
    """등록된 계좌 목록(드롭다운 선택용). 자동매매 account_id 선택에 쓴다."""
    accounts = await AccountRepository(session).list_all()
    return [
        AccountRead(
            id=a.id, account_type=a.account_type.value,
            broker_account_no=a.broker_account_no, alias=a.alias,
        )
        for a in accounts
    ]


# --- MANUAL-SELL-RECON-2: read-only reconciliation report ---------------------
class ReconciliationReportItemRead(BaseModel):
    symbol_code: str
    symbol_name: str | None = None
    report_type: str
    broker_quantity: int | None = None
    db_quantity: int | None = None
    broker_avg_price: Decimal | None = None
    db_avg_price: Decimal | None = None
    details: str


class ManualReconciliationReportResponse(BaseModel):
    account_id: int
    broker_account_no: str | None = None
    market: str
    checked_at: datetime
    broker_holdings_count: int
    db_open_positions_count: int
    matched_count: int
    mismatch_count: int
    mismatches: list[ReconciliationReportItemRead]
    broker_only_holdings: list[ReconciliationReportItemRead]
    db_only_positions: list[ReconciliationReportItemRead]
    matched_positions: list[ReconciliationReportItemRead]
    warnings: list[str]


@router.get(
    "/{account_id}/reconciliation-report",
    response_model=ManualReconciliationReportResponse,
)
async def get_reconciliation_report(
    account_id: int,
    market: str = "KR",
    symbols: list[str] | None = Query(default=None),
    include_zero_quantity_db_positions: bool = False,
    session: AsyncSession = Depends(get_db),
    broker: BrokerClient = Depends(get_broker_client),
) -> ManualReconciliationReportResponse:
    """KIS holdings ↔ DB positions를 비교하는 **read-only** 정합성 리포트.

    DB를 수정하지 않으며 기존 auto-sync/reconcile write 경로를 호출하지 않는다. 수동 앱 매도 후
    자동매매 재개 전 불일치를 확인하는 용도. 불일치 해소(DB reconciliation)는 별도 human-approved 작업.
    """
    service = ManualReconciliationReportService(session, broker)
    try:
        report = await service.build_report(
            account_id,
            market=market,
            symbols=symbols,
            include_zero_quantity_db_positions=include_zero_quantity_db_positions,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except KISAPIError as e:
        raise HTTPException(status_code=502, detail=e.msg1) from e
    return ManualReconciliationReportResponse.model_validate(report, from_attributes=True)


# --- PAPER-RESUME-1: read-only resume readiness checklist ---------------------
class CheckItemRead(BaseModel):
    key: str
    status: str  # PASS / WARN / BLOCK / INFO
    message: str
    details: dict = {}


class PaperResumeReadinessResponse(BaseModel):
    account_id: int
    overall_status: str  # READY / READY_WITH_WARNINGS / BLOCKED
    checked_at: datetime
    pass_count: int
    warn_count: int
    block_count: int
    items: list[CheckItemRead]


@router.get(
    "/{account_id}/paper-resume-readiness",
    response_model=PaperResumeReadinessResponse,
)
async def get_paper_resume_readiness(
    account_id: int,
    session: AsyncSession = Depends(get_db),
    broker: BrokerClient = Depends(get_broker_client),
) -> PaperResumeReadinessResponse:
    """제한된 paper 자동 주문 재개 **전** 점검용 read-only checklist.

    자동매매를 켜지 않으며 DB/RiskConfig/scheduler/settings를 수정하지 않는다. 각 항목을
    PASS/WARN/BLOCK/INFO로 보고하고 overall_status(READY/READY_WITH_WARNINGS/BLOCKED)를 반환한다.
    """
    service = PaperResumeReadinessService(session, broker)
    try:
        report = await service.build_checklist(account_id)
    except KISAPIError as e:
        raise HTTPException(status_code=502, detail=e.msg1) from e
    return PaperResumeReadinessResponse.model_validate(report, from_attributes=True)
