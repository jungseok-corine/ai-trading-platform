from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """기본 CRUD만 제공하는 제네릭 Repository."""

    model: type[ModelType]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id_: Any) -> ModelType | None:
        return await self.session.get(self.model, id_)

    async def list(self, limit: int = 100, offset: int = 0) -> list[ModelType]:
        result = await self.session.execute(select(self.model).limit(limit).offset(offset))
        return list(result.scalars().all())

    async def create(self, **kwargs: Any) -> ModelType:
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def update(self, instance: ModelType, **kwargs: Any) -> ModelType:
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await self.session.flush()
        return instance

    async def delete(self, instance: ModelType) -> None:
        await self.session.delete(instance)
        await self.session.flush()
