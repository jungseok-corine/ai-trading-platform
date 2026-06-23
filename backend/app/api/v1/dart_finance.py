"""DART 재무제표 수집 · 조회 API (C-2.21.1).

read-only 수집 — 주문과 무관하다. DART_API_KEY 미설정이면 422 반환.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.repositories.financial_statement import FinancialStatementRepository
from app.services.dart_finance_ingest_service import DartFinanceIngestService, FinanceIngestSummary
from app.services.dart_finance_provider import DartFinanceProviderError

router = APIRouter(prefix="/dart/finance", tags=["dart-finance"])


class FinanceIngestRequest(BaseModel):
    symbols: list[str] | None = None
    bsns_years: list[str] | None = None  # 미지정 시 최근 2년


class FinanceIngestSummaryRead(BaseModel):
    symbols_attempted: int
    symbols_ok: int
    symbols_failed: int
    records_upserted: int
    errors: list[str]


@router.post("/ingest", response_model=FinanceIngestSummaryRead)
async def ingest_financials(
    payload: FinanceIngestRequest,
    session: AsyncSession = Depends(get_db),
) -> FinanceIngestSummaryRead:
    """watchlist(또는 지정 종목)의 재무제표를 DART에서 수집해 저장한다."""
    try:
        summary: FinanceIngestSummary = await DartFinanceIngestService(session).ingest(
            symbols=payload.symbols,
            bsns_years=payload.bsns_years,
        )
    except DartFinanceProviderError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return FinanceIngestSummaryRead(**summary.to_dict())


@router.get("/{stock_code}")
async def get_financials(
    stock_code: str,
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """종목 코드로 저장된 재무제표 요약 목록을 반환한다(최신순, 최대 10건)."""
    repo = FinancialStatementRepository(session)
    rows = await repo.list_by_stock_code(stock_code, limit=10)
    return [
        {
            "id": r.id,
            "corp_code": r.corp_code,
            "stock_code": r.stock_code,
            "corp_name": r.corp_name,
            "bsns_year": r.bsns_year,
            "reprt_code": r.reprt_code,
            "fs_div": r.fs_div,
            "key_items": r.key_items,
            "raw_count": r.raw_count,
            "collected_at": r.collected_at.isoformat() if r.collected_at else None,
        }
        for r in rows
    ]
