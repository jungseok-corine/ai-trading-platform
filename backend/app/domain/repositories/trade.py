from app.domain.models.trade import Trade
from app.domain.repositories.base import BaseRepository


class TradeRepository(BaseRepository[Trade]):
    model = Trade
