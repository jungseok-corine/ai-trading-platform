"""전략 카탈로그 API (C-7.2).

유명 전략 DSL 스펙을 백테스트 입학시험에 응시시키고 통과분만 pending 제안으로.
승인은 사람 — 이 API는 어떤 전략도 직접 배치하지 않는다.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.strategy_catalog import CATALOG, StrategyCatalogService

router = APIRouter(prefix="/strategy-catalog", tags=["strategy-catalog"])


@router.get("")
async def list_catalog() -> list[dict]:
    """카탈로그 목록 (스펙+출처, read-only)."""
    return [
        {"name": e["spec"]["name"], "source": e["spec"]["source"], "regime_fit": e["regime_fit"]}
        for e in CATALOG
    ]


@router.post("/seed")
async def seed_catalog(
    exam_days: int = Query(365, ge=30, le=730),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """카탈로그 전체 입학시험 실행 — 통과분만 pending 제안 생성 (멱등: 중복 제목 skip)."""
    return await StrategyCatalogService(session).seed_and_validate(exam_days=exam_days)
