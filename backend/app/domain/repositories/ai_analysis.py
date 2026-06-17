from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.domain.models.ai_analysis import AiAnalysisRun, AiModelResponse
from app.domain.repositories.base import BaseRepository


class AiAnalysisRunRepository(BaseRepository[AiAnalysisRun]):
    model = AiAnalysisRun

    async def get_with_responses(self, run_id: int) -> AiAnalysisRun | None:
        # populate_existing=True: identity map에 캐시된 객체가 있어도
        # selectinload가 응답 관계를 새로 로드하도록 강제한다.
        result = await self.session.execute(
            select(AiAnalysisRun)
            .where(AiAnalysisRun.id == run_id)
            .options(selectinload(AiAnalysisRun.responses))
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def list_by_strategy_version(
        self,
        strategy_id: int,
        version_id: int,
        limit: int = 20,
    ) -> list[AiAnalysisRun]:
        # id DESC: created_at은 동일 ms 내 여러 INSERT 시 동일값이 될 수 있으므로
        # auto-increment id를 기준으로 정렬한다.
        result = await self.session.execute(
            select(AiAnalysisRun)
            .where(
                AiAnalysisRun.strategy_id == strategy_id,
                AiAnalysisRun.strategy_version_id == version_id,
            )
            .options(selectinload(AiAnalysisRun.responses))
            .execution_options(populate_existing=True)
            .order_by(AiAnalysisRun.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class AiModelResponseRepository(BaseRepository[AiModelResponse]):
    model = AiModelResponse

    async def list_by_run(self, run_id: int) -> list[AiModelResponse]:
        result = await self.session.execute(
            select(AiModelResponse)
            .where(AiModelResponse.run_id == run_id)
            .order_by(AiModelResponse.created_at.asc())
        )
        return list(result.scalars().all())
