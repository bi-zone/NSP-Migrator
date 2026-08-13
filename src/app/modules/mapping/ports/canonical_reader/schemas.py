"""
Duplicates models from modules/canonical/application/dto - to isolate modules
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


# -- Canonical zones, objects (addr, services) schemas
class CanonicalAddrObjKind(StrEnum):
    HOST = "host"
    SUBNET = "subnet"
    RANGE = "range"
    FQDN = "fqdn"
    ANY_ADDR = "any_addr"
    UNRESOLVED_ADDR = "unresolved_addr"
    ADDR_GROUP = "addr_group"


class CanonicalServiceKind(StrEnum):
    TCP = "tcp"
    UDP = "udp"
    ICMP = "icmp"
    IP_PROTO = "ip_proto"
    ANY_SERVICE = "any_service"
    SERVICE_GROUP = "service_group"
    UNRESOLVED_SERVICE = "unresolved_service"


@dataclass(frozen=True, slots=True)
class CanonicalScopeEntities:
    """Zones, AddrObjects, Service of selected scope of Canonical Rules"""

    zones: list["CanonicalZone"]
    addr_objects: list["CanonicalAddrObject"]
    services: list["CanonicalService"]


@dataclass(frozen=True, slots=True)
class CanonicalZone:
    id: UUID
    zone_key: str
    name: str


@dataclass(frozen=True, slots=True)
class CanonicalAddrObject:
    id: UUID
    kind: CanonicalAddrObjKind
    name: str
    parent_id: UUID | None = None
    parent_ids: tuple[UUID, ...] = ()

    cidr: str | None = None
    range_start: str | None = None
    range_end: str | None = None
    fqdn: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalService:
    id: UUID
    kind: CanonicalServiceKind
    name: str
    parent_id: UUID | None = None
    parent_ids: tuple[UUID, ...] = ()

    protocol: str | None = None
    port_from: int | None = None
    port_to: int | None = None
    icmp_type: int | None = None
    icmp_code: int | None = None


# -- Canonical Rules schemas
class CanonicalRuleOperandRole(StrEnum):
    """
    Operand role as seen by mapping module.

    Values intentionally mirror canonical OperandRole values, but this enum
    belongs to mapping module boundary.
    """

    SRC_ZONE = "src_zone"
    DST_ZONE = "dst_zone"
    SRC_OBJECT = "src_object"
    DST_OBJECT = "dst_object"
    SERVICE = "service"


@dataclass(frozen=True, slots=True)
class CanonicalRuleOperand:
    """
    Canonical rule operand converted to mapping module boundary model.

    For zone roles:
        target_zone_id must be filled.

    For address/service roles:
        target_object_id must be filled.
    """

    id: UUID
    rule_id: UUID
    role: CanonicalRuleOperandRole

    target_zone_id: UUID | None
    target_object_id: UUID | None


class CanonicalRuleAction(StrEnum):
    """Mirror from canonical"""

    PERMIT = "PERMIT"
    DENY = "DENY"


@dataclass(frozen=True, slots=True)
class CanonicalRule:
    """
    Canonical rule skeleton required for mapped rule preview.
    """

    id: UUID
    canonical_snapshot_id: UUID
    name: str
    action: CanonicalRuleAction

    operands: list[CanonicalRuleOperand]
