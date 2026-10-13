from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.integrations.sdwan_csp_api.gateways.enums import SdwanRulePriority


class MappedRuleDataAction(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


@dataclass(frozen=True, slots=True)
class MappedRuleData:
    """Mapped rule body with selected SD-WAN object ids grouped by operand role."""

    id: UUID
    name: str
    action: MappedRuleDataAction
    priority: int
    src_zones: list[int]
    dst_zones: list[int]
    src_addr_objects: list[int]
    dst_addr_objects: list[int]
    services: list[int]


@dataclass(frozen=True, slots=True)
class MappingScopeData:
    """Minimal Mapping scope data needed by execute module."""

    id: UUID
    title: str
    csp_profile_id: UUID
    vpc_id: str
    sdwan_target_id: str
    rules_priority: SdwanRulePriority
    catalog_fingerprint: str
