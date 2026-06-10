from app.domain.models.market_data import MarketData
from app.domain.repositories.base import BaseRepository


class MarketDataRepository(BaseRepository[MarketData]):
    model = MarketData
