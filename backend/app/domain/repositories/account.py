from sqlalchemy import select

from app.domain.models.account import Account
from app.domain.repositories.base import BaseRepository


class AccountRepository(BaseRepository[Account]):
    model = Account

    async def get_by_broker_account_no(self, broker_account_no: str) -> Account | None:
        result = await self.session.execute(
            select(Account).where(Account.broker_account_no == broker_account_no)
        )
        return result.scalars().first()

    async def list_all(self) -> list[Account]:
        result = await self.session.execute(select(Account).order_by(Account.id))
        return list(result.scalars().all())
