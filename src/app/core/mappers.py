from abc import ABC, abstractmethod
from typing import Generic, TypeVar

DomainT = TypeVar("DomainT")
ModelT = TypeVar("ModelT")
SchemaT = TypeVar("SchemaT")


class IBaseDomainModelMapper(ABC, Generic[DomainT, ModelT]):
    @abstractmethod
    def to_domain(self, model: ModelT) -> DomainT: ...

    @abstractmethod
    def to_model(self, entity: DomainT) -> ModelT: ...


class IBaseDomainSchemaMapper(ABC, Generic[DomainT, SchemaT]):
    @abstractmethod
    def to_domain(self, model: SchemaT) -> DomainT: ...

    @abstractmethod
    def to_schema(self, entity: DomainT) -> SchemaT: ...
