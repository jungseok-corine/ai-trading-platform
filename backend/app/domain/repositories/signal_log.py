from app.domain.models.signal_log import SignalLog
from app.domain.repositories.base import BaseRepository


class SignalLogRepository(BaseRepository[SignalLog]):
    model = SignalLog
