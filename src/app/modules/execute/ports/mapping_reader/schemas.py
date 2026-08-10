from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class MappedRuleDataAction(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


@dataclass(frozen=True, slots=True)
class MappedRuleData:
    """Mapped rule body with selected SD-WAN object ids grouped by operand role."""

    id: UUID
    action: MappedRuleDataAction
    src_zones: list[int]
    dst_zones: list[int]
    src_addr_objects: list[int]
    dst_addr_objects: list[int]
    services: list[int]


@dataclass(frozen=True, slots=True)
class MappingScopeData:
    """Minimal Mapping scope data needed by execute module."""

    id: UUID
    sdwan_target_id: str
