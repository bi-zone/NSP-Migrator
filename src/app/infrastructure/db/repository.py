from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

TModel = TypeVar("TModel")
TModelID = TypeVar("TModelID")


class SqlAlchemyRepository(Generic[TModel, TModelID]):
    def __init__(self, session: AsyncSession, model: type[TModel]) -> None:
        self.session = session
        self.model = model

    # TODO:: разобраться с UUID и ID
    async def get_by_id(self, entity_id: TModelID) -> TModel | None:
        try:
            return await self.session.get_one(self.model, entity_id)
        except NoResultFound:
            return None

    async def get_list(self) -> list[TModel]:
        return list((await self.session.scalars(select(self.model))).all())

    async def add(self, entity: TModel) -> TModel:
        """Add model to session and make flush"""
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def add_bulk(self, entities: list[TModel]) -> None:
        self.session.add_all(entities)
        await self.session.flush()

    async def delete_by_id(self, entity_id: TModelID) -> None:
        entity = await self.get_by_id(entity_id)
        if entity is not None:
            await self.session.delete(entity)
            await self.session.flush()

    async def save(self, entity: TModel) -> TModel:
        await self.session.merge(entity)
        return entity
