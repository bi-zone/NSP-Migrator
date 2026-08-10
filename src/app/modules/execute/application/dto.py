from dataclasses import dataclass
from typing import Any, Literal

from app.modules.execute.domain.enums import SdwanRuleAction


@dataclass(slots=True, frozen=True)
class SdwanAddrObjectDTO:
    type: str
    id: int


@dataclass(slots=True, frozen=True)
class AmbiguousReasonDTO:
    code: int
    meta: dict


@dataclass(slots=True, frozen=True)
class SdwanRuleDTO:
    """Display DTO for policy objects fetched from SD-WAN by ids."""

    type: Literal["policy"]  # ignore null_policy
    policy_id: int
    parents: list[str]
    order: str
    priority: Literal["pre", "local", "post"]
    name: str
    description: str
    tags: list[str]
    activated: bool
    action: SdwanRuleAction
    log: bool
    l4_inspection: bool
    ambiguous: bool
    ambiguous_reason: AmbiguousReasonDTO | None
    created_at: str
    updated_at: str
    snat: dict | None
    dnat: dict | None

    ingress_zone: list[int]
    egress_zone: list[int]

    src_address: list[SdwanAddrObjectDTO]
    dst_address: list[SdwanAddrObjectDTO]

    service: list[int]

    src_idents: list[Any]
    dst_idents: list[Any]
