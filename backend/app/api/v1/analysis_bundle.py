"""분석 번들(매매 테이프) 온디맨드 API (C-2.52).

사람이 요청할 때만 조립한다(평소 준비 안 함). LLM 호출/토큰 없음 — DB 원본에서
압축·사전계산된 번들만 반환한다. 이후 단계에서 이 번들이 LLM 분석 입력이 된다.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import MarketCode
from app.services.analysis_bundle_service import AnalysisBundleService
from app.services.trade_tape_service import TradeTapeService

router = APIRouter(prefix="/analysis-bundle", tags=["analysis-bundle"])


def get_service(session: AsyncSession = Depends(get_db)) -> TradeTapeService:
    return TradeTapeService(session)


def get_bundle_service(session: AsyncSession = Depends(get_db)) -> AnalysisBundleService:
    return AnalysisBundleService(session)


@router.get("/trade-tape")
async def get_trade_tape(
    strategy_version_id: int = Query(...),
    trading_day: date = Query(..., description="KST 거래일 (YYYY-MM-DD)"),
    timeframe: str = Query(default="1m"),
    window: int = Query(default=15, ge=0, le=60, description="매매 ±N분 상세 유지"),
    coarse: int = Query(default=15, ge=2, le=60, description="나머지 구간 집계 단위(개)"),
    service: TradeTapeService = Depends(get_service),
) -> dict:
    """전략 버전의 그날 매매 테이프(압축+사전계산 번들)를 반환한다."""
    tape = await service.build_for_version(
        strategy_version_id, trading_day, timeframe=timeframe, window=window, coarse=coarse
    )
    if tape is None:
        raise HTTPException(status_code=404, detail="strategy version not found")
    return tape


@router.get("/full")
async def get_full_bundle(
    strategy_version_id: int = Query(...),
    trading_day: date = Query(..., description="KST 거래일 (YYYY-MM-DD)"),
    market: MarketCode = Query(default=MarketCode.KR),
    analyst_note: str | None = Query(default=None, description="사람이 직접 주입하는 분석 노트"),
    service: AnalysisBundleService = Depends(get_bundle_service),
) -> dict:
    """전략 입력 + 매매 테이프 + 매크로 + 뉴스 + 수동노트를 합친 전체 분석 번들(온디맨드)."""
    bundle = await service.build_full(
        strategy_version_id, trading_day, market=market, analyst_note=analyst_note
    )
    if bundle is None:
        raise HTTPException(status_code=404, detail="strategy version not found")
    return bundle
