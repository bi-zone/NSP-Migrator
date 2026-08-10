from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.execute.ports.mapping_reader.schemas import (
    MappedRuleData,
    MappingScopeData,
)


class MappingReaderPort(ABC):
    @abstractmethod
    async def get_mapping_scope_rules(
        self, mapping_scope_id: UUID
    ) -> list[MappedRuleData]: ...

    @abstractmethod
    async def get_mapping_scope_data(
        self, mapping_scope_id: UUID
    ) -> MappingScopeData: ...
