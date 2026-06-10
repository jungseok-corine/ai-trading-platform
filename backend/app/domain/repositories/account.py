from app.domain.models.account import Account
from app.domain.repositories.base import BaseRepository


class AccountRepository(BaseRepository[Account]):
    model = Account
