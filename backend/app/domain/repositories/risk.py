from app.domain.models.risk import RiskConfig, RiskEvent
from app.domain.repositories.base import BaseRepository


class RiskConfigRepository(BaseRepository[RiskConfig]):
    model = RiskConfig


class RiskEventRepository(BaseRepository[RiskEvent]):
    model = RiskEvent
