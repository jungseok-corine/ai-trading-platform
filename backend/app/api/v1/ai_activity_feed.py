"""AI 의사결정 피드 API (C-6.7). read-only 타임라인 집계."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.ai_activity_feed_service import AiActivityFeedService

router = APIRouter(prefix="/ai-activity-feed", tags=["ai-activity-feed"])


@router.get("")
async def get_feed(
    days: int = Query(1, ge=1, le=30),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await AiActivityFeedService(session).feed(days=days, limit=limit)
