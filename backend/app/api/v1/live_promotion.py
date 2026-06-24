"""실전 승격 심사 게이트 API (C-2.29).

실전 승격은 '자동매매 시작'이 아니라 '사람이 심사를 승인했다는 감사 로그'다.
StrategyVersion.status, 자동매매 플래그, 실전 거래 활성화 환경변수는 변경하지 않는다.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.live_promotion_gate_service import (
    LivePromotionAlreadyApprovedError,
    LivePromotionCriteriaNotFoundError,
    LivePromotionGateService,
    LivePromotionNotConfirmedError,
    LivePromotionReadinessFailedError,
    LivePromotionVersionNotFoundError,
)

router = APIRouter(tags=["live_promotion"])


def get_service(session: AsyncSession = Depends(get_db)) -> LivePromotionGateService:
    return LivePromotionGateService(session)


# ── 응답 스키마 ──────────────────────────────────────────────────────────────

class CheckRead(BaseModel):
    name: str
    passed: bool
    actual: str
    threshold: str


class LiveReadinessReportRead(BaseModel):
    strategy_version_id: int
    criteria_id: int | None
    passed: bool
    trades_count: int
    days: int
    expectancy: float
    max_drawdown: float
    checks: list[CheckRead]
    intel_context: dict | None
    evaluation_id: int | None


class LivePromotionRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_version_id: int
    promotion_evaluation_id: int | None
    status: str
    criteria_passed: bool
    readiness_snapshot: dict | None
    risk_snapshot: dict | None
    approved_at: datetime
    approved_by: str
    note: str | None
    created_at: datetime


class LivePromoteRequest(BaseModel):
    confirmed: bool = False
    confirmed_by: str = ""
    note: str | None = None


class LivePromoteResponse(BaseModel):
    record: LivePromotionRecordRead
    readiness_snapshot: dict | None
    message: str


# ── 엔드포인트 ──────────────────────────────────────────────────────────────

@router.get(
    "/strategy-versions/{version_id}/live-readiness",
    response_model=LiveReadinessReportRead,
)
async def get_live_readiness(
    version_id: int,
    criteria_id: int | None = Query(default=None),
    service: LivePromotionGateService = Depends(get_service),
) -> LiveReadinessReportRead:
    """전략 버전의 실전 승격 준비도를 평가한다."""
    try:
        report = await service.check_readiness(version_id, criteria_id=criteria_id)
    except LivePromotionVersionNotFoundError:
        raise HTTPException(status_code=404, detail="strategy version not found")
    except LivePromotionCriteriaNotFoundError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return LiveReadinessReportRead(
        strategy_version_id=report.strategy_version_id,
        criteria_id=report.criteria_id,
        passed=report.passed,
        trades_count=report.trades_count,
        days=report.days,
        expectancy=report.expectancy,
        max_drawdown=report.max_drawdown,
        checks=[CheckRead(**c) for c in report.checks],
        intel_context=report.intel_context,
        evaluation_id=report.evaluation_id,
    )


@router.post(
    "/strategy-versions/{version_id}/live-promote",
    response_model=LivePromoteResponse,
    status_code=201,
)
async def approve_live_promotion(
    version_id: int,
    payload: LivePromoteRequest,
    criteria_id: int | None = Query(default=None),
    service: LivePromotionGateService = Depends(get_service),
) -> LivePromoteResponse:
    """사람이 명시적으로 실전 승격 심사를 승인한다.

    이 API는 실전 자동매매를 시작하지 않는다. 감사 로그를 남길 뿐이다.
    """
    try:
        record = await service.approve_live_promotion(
            strategy_version_id=version_id,
            confirmed_by=payload.confirmed_by,
            note=payload.note,
            confirmed=payload.confirmed,
            criteria_id=criteria_id,
        )
    except LivePromotionNotConfirmedError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except LivePromotionVersionNotFoundError:
        raise HTTPException(status_code=404, detail="strategy version not found")
    except LivePromotionCriteriaNotFoundError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except LivePromotionReadinessFailedError as e:
        raise HTTPException(
            status_code=422,
            detail=f"readiness criteria not met: {e.failed_checks}",
        )
    except LivePromotionAlreadyApprovedError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return LivePromoteResponse(
        record=LivePromotionRecordRead.model_validate(record),
        readiness_snapshot=record.readiness_snapshot,
        message="Live promotion approved for review only. Real trading remains disabled.",
    )
