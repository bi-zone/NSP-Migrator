"""Domain enums for canonical snapshots, objects, and rule operands.

Values are persisted in PostgreSQL and exposed via HTTP/OpenAPI schemas.
Changing enum members is a breaking contract for mapping and Streamlit UI.
"""

from enum import StrEnum


class SnapshotStatus(StrEnum):
    """Canonical snapshot materialization lifecycle."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class ObjectFamily(StrEnum):
    """Top-level object classification."""

    ADDR = "addr"
    SERVICE = "service"


class ObjectKind(StrEnum):
    """Concrete object kind within a family.

    Group kinds (ADDR_GROUP, SERVICE_GROUP) participate in BFS
    expansion in services/group_expansion.expand_object_groups.
    """

    # -- address leafs
    HOST = "host"
    SUBNET = "subnet"
    RANGE = "range"
    FQDN = "fqdn"
    ANY_ADDR = "any_addr"
    UNRESOLVED_ADDR = "unresolved_addr"

    # -- service leafs
    TCP = "tcp"
    UDP = "udp"
    ICMP = "icmp"
    IP_PROTO = "ip_proto"
    ANY_SERVICE = "any_service"
    UNRESOLVED_SERVICE = "unresolved_service"

    # -- groups (expanded transitively in rule_scope)
    ADDR_GROUP = "addr_group"
    SERVICE_GROUP = "service_group"


class OperandRole(StrEnum):
    """Rule operand slot referencing a zone or object."""

    SRC_ZONE = "src_zone"
    DST_ZONE = "dst_zone"
    SRC_OBJECT = "src_object"
    DST_OBJECT = "dst_object"
    SERVICE = "service"
