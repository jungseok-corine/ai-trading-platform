"""DART 공시 수집 API (C-2.59).

보유/관심 종목의 중요 공시를 가져와 news_events에 저장한다(중요도 미달은 제외).
read-only 수집이며 주문과 무관하다. 기본 provider 키 없으면 422.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.dart_ingest_service import DartIngestService
from app.services.dart_provider import DartProviderError
from app.services.disclosure_alert_service import DisclosureAlertService
from app.services.disclosure_assessment_service import DisclosureAssessmentService

router = APIRouter(prefix="/dart", tags=["dart"])


def get_service(session: AsyncSession = Depends(get_db)) -> DartIngestService:
    return DartIngestService(session)


def get_alert_service(session: AsyncSession = Depends(get_db)) -> DisclosureAlertService:
    return DisclosureAlertService(session)


def get_assessment_service(
    session: AsyncSession = Depends(get_db),
) -> DisclosureAssessmentService:
    return DisclosureAssessmentService(session)


@router.get("/alerts")
async def list_alerts(
    hours: int = Query(default=48, ge=1, le=720),
    service: DisclosureAlertService = Depends(get_alert_service),
) -> list[dict]:
    """최근 보유/관심 종목의 중요 공시 알림(최신순)."""
    return await service.recent(hours=hours)


@router.post("/assess")
async def assess_disclosure(
    news_event_id: int = Query(...),
    holding_note: str | None = Query(default=None),
    service: DisclosureAssessmentService = Depends(get_assessment_service),
) -> dict:
    """공시 한 건의 보유 포지션 영향을 LLM으로 평가한다(온디맨드). AI는 평가만, 대응은 사람."""
    result = await service.assess(news_event_id, holding_note=holding_note)
    if result is None:
        raise HTTPException(status_code=404, detail="news event not found")
    return result


class DartIngestRequest(BaseModel):
    # None이면 enabled watchlist 종목을 모니터 대상으로 한다.
    symbols: list[str] | None = None
    trading_day: date | None = None


class DartIngestSummaryRead(BaseModel):
    fetched: int
    matched: int
    material: int
    created: int
    skipped_existing: int


@router.post("/ingest", response_model=DartIngestSummaryRead)
async def ingest_disclosures(
    payload: DartIngestRequest,
    service: DartIngestService = Depends(get_service),
) -> DartIngestSummaryRead:
    """최근 공시를 가져와 모니터 종목·중요도로 필터해 저장한다."""
    try:
        summary = await service.ingest(
            symbols=payload.symbols, trading_day=payload.trading_day
        )
    except DartProviderError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return DartIngestSummaryRead(**summary.to_dict())
