from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.repositories.base import BaseRepository


class StrategyRepository(BaseRepository[Strategy]):
    model = Strategy


class StrategyVersionRepository(BaseRepository[StrategyVersion]):
    model = StrategyVersion
