"""일일 AI 리서치 리포트 API (C-2.29).

매일 장마감 후 시장/전략/스캐너/체결 활동을 집계한 리포트를 생성·조회한다.
주문과 무관하며, 분석/리포트 전용이다.
"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import MarketCode
from app.services.daily_report_service import DailyReportService

router = APIRouter(prefix="/daily-reports", tags=["daily-reports"])


def get_service(session: AsyncSession = Depends(get_db)) -> DailyReportService:
    return DailyReportService(session)


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market: MarketCode
    report_date: date
    summary: str | None
    sections: dict | None
    created_at: datetime
    updated_at: datetime


@router.post("/generate", response_model=ReportRead, status_code=201)
async def generate_report(
    report_date: date | None = Query(default=None),
    market: MarketCode = Query(default=MarketCode.KR),
    service: DailyReportService = Depends(get_service),
) -> ReportRead:
    """report_date(기본 오늘)의 활동을 집계해 리포트를 생성/갱신한다."""
    report = await service.generate(report_date=report_date, market=market)
    return ReportRead.model_validate(report)


@router.get("", response_model=list[ReportRead])
async def list_reports(
    market: MarketCode | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=200),
    service: DailyReportService = Depends(get_service),
) -> list[ReportRead]:
    reports = await service.list_reports(market=market, limit=limit)
    return [ReportRead.model_validate(r) for r in reports]


@router.get("/{report_date}", response_model=ReportRead)
async def get_report(
    report_date: date,
    market: MarketCode = Query(default=MarketCode.KR),
    service: DailyReportService = Depends(get_service),
) -> ReportRead:
    report = await service.get_report(report_date, market=market)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return ReportRead.model_validate(report)
