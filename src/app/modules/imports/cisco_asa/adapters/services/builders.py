from __future__ import annotations

from uuid import UUID

from app.modules.canonical.domain import CanonicalObject, ObjectFamily, ObjectKind
from app.modules.imports.cisco_asa.adapters.services.common import (
    _ICMP_NAME_TO_TYPE,
    ip_protocol_object_key,
    kind_for_protocol,
    service_object_key,
)
from app.modules.imports.cisco_asa.domain.parsed_config import ParsedServiceObject
from app.modules.imports.cisco_asa.parsing.service_catalog import (
    lookup_builtin_service,
    parse_port_token,
)

_MIN_PORT = 0
_MAX_PORT = 65535


def resolve_l4_destination_range(payload: dict) -> tuple[int, int] | None:
    """Resolve an exactly representable TCP/UDP destination port constraint.

    An absent constraint represents the full ``0..65535`` range. Destination
    ``eq``, ``range``, ``lt`` and ``gt`` operators are converted to one closed
    range. ``None`` is returned for source-port constraints, ``neq`` (which
    requires two ranges), malformed payloads and out-of-bounds values.
    """

    if payload.get("source_op") is not None or payload.get("raw") is not None:
        return None

    operator = payload.get("destination_op", payload.get("op"))
    port_value = payload.get("destination_port", payload.get("port"))
    port_from_value = payload.get("destination_port_from", payload.get("port_from"))
    port_to_value = payload.get("destination_port_to", payload.get("port_to"))

    if operator is None:
        if any(
            value is not None for value in (port_value, port_from_value, port_to_value)
        ):
            return None
        return _MIN_PORT, _MAX_PORT

    if operator == "range":
        port_from = parse_port_token(str(port_from_value))
        port_to = parse_port_token(str(port_to_value))
        if (
            port_from is None
            or port_to is None
            or not _MIN_PORT <= port_from <= port_to <= _MAX_PORT
        ):
            return None
        return port_from, port_to

    port = parse_port_token(str(port_value))
    if port is None or not _MIN_PORT <= port <= _MAX_PORT:
        return None

    if operator == "eq":
        return port, port
    if operator == "lt" and port > _MIN_PORT:
        return _MIN_PORT, port - 1
    if operator == "gt" and port < _MAX_PORT:
        return port + 1, _MAX_PORT

    return None


def _build_unresolved_l4_service(
    *,
    canonical_snapshot_id: UUID,
    name: str,
    object_key: str,
    protocol: str,
    description: str | None,
) -> CanonicalObject:
    return CanonicalObject.create(
        canonical_snapshot_id=canonical_snapshot_id,
        object_key=object_key,
        object_family=ObjectFamily.SERVICE,
        object_kind=ObjectKind.UNRESOLVED_SERVICE,
        name=name,
        protocol=protocol,
        description=description,
    )


def build_canonical_service_from_payload(
    *,
    canonical_snapshot_id: UUID,
    name: str,
    object_key: str,
    payload: dict,
) -> CanonicalObject | None:
    """Build one leaf service object from a parsed service payload dict.

    Used by canonical_object_for_parsed_service (object headers) and
    members._register_service_payload / port-object handling during
    group-member materialization.

    Returns None for unsupported protocol/shape combinations — callers
    treat that as "could not materialize" (skip member edge or use header
    fallback).

    Supported shapes include protocol-wide TCP/UDP, exactly representable
    destination port constraints, TCP-UDP eq expansion, ICMP, IP-level
    protocols, and numeric IP protocol identifiers. TCP/UDP constraints that
    cannot be represented exactly become UNRESOLVED_SERVICE objects.
    """
    proto = (payload.get("protocol") or "").lower()
    if not proto:
        return None

    if (
        proto == "tcp-udp"
        and payload.get("op") == "eq"
        and payload.get("port") is not None
    ):
        port = parse_port_token(str(payload["port"]))
        if port is None:
            return None
        return CanonicalObject.create(
            canonical_snapshot_id=canonical_snapshot_id,
            object_key=object_key,
            object_family=ObjectFamily.SERVICE,
            object_kind=ObjectKind.IP_PROTO,
            name=f"tcp-udp:{port}-{port}",
            protocol="tcp-udp",
            port_from=port,
            port_to=port,
            description="expanded tcp-udp service-object member",
        )

    if proto in {"tcp", "udp"}:
        port_range = resolve_l4_destination_range(payload)
        if port_range is None:
            return _build_unresolved_l4_service(
                canonical_snapshot_id=canonical_snapshot_id,
                name=name,
                object_key=object_key,
                protocol=proto,
                description=payload.get("description"),
            )

        return CanonicalObject.create(
            canonical_snapshot_id=canonical_snapshot_id,
            object_key=object_key,
            object_family=ObjectFamily.SERVICE,
            object_kind=kind_for_protocol(proto),
            name=name,
            protocol=proto,
            port_from=port_range[0],
            port_to=port_range[1],
            description=payload.get("description"),
        )

    if proto in {"icmp", "icmp6"}:
        icmp_name = (payload.get("icmp") or "").lower().replace(" ", "-")
        icmp_type = _ICMP_NAME_TO_TYPE.get(icmp_name)
        return CanonicalObject.create(
            canonical_snapshot_id=canonical_snapshot_id,
            object_key=object_key,
            object_family=ObjectFamily.SERVICE,
            object_kind=ObjectKind.ICMP,
            name=name,
            protocol=proto,
            icmp_type=icmp_type,
            description=payload.get("description"),
        )

    if proto in {"ip", "esp", "ah", "gre"}:
        return CanonicalObject.create(
            canonical_snapshot_id=canonical_snapshot_id,
            object_key=object_key,
            object_family=ObjectFamily.SERVICE,
            object_kind=ObjectKind.IP_PROTO,
            name=name,
            protocol=proto,
            description=payload.get("description"),
        )

    if proto.isdigit():
        return CanonicalObject.create(
            canonical_snapshot_id=canonical_snapshot_id,
            object_key=object_key,
            object_family=ObjectFamily.SERVICE,
            object_kind=ObjectKind.IP_PROTO,
            name=f"ip-proto-{proto}",
            protocol=proto,
            description=payload.get("description"),
        )

    return None


def build_inline_service_from_ref(
    *,
    canonical_snapshot_id: UUID,
    protocol: str,
    ref: str,
) -> CanonicalObject | None:
    """Materialize a service object from an ACL inline port/service operand.

    Called from _ServiceNormalizationMixin._ensure_service_object_from_ref
    when a named service:{ref} object does not exist. Parses numeric port
    or range tokens, then falls back to lookup_builtin_service for aliases
    like www or ssh.

    Object keys follow service_object_key convention (e.g.
    service:tcp:80-80 asserted in test_normalizer_fixtures.py).

    Returns:
        Built object, or None when operand cannot be interpreted (caller
        routes to unresolved-service fallback).
    """
    proto = protocol.lower()
    ref = ref.strip()

    if proto in {"tcp", "udp"}:
        if "-" in ref:
            parts = ref.split("-", 1)
            p_from = parse_port_token(parts[0])
            p_to = parse_port_token(parts[1])
        else:
            p_from = parse_port_token(ref)
            p_to = p_from
        if p_from is not None and p_to is not None:
            key = service_object_key(proto, p_from, p_to)
            kind = kind_for_protocol(proto)
            return CanonicalObject.create(
                canonical_snapshot_id=canonical_snapshot_id,
                object_key=key,
                object_family=ObjectFamily.SERVICE,
                object_kind=kind,
                name=f"{proto}:{p_from}-{p_to}",
                protocol=proto,
                port_from=p_from,
                port_to=p_to,
            )

        entry = lookup_builtin_service(ref, protocol_hint=proto)
        if entry is not None:
            key = service_object_key(entry.protocol, entry.port_from, entry.port_to)
            return CanonicalObject.create(
                canonical_snapshot_id=canonical_snapshot_id,
                object_key=key,
                object_family=ObjectFamily.SERVICE,
                object_kind=kind_for_protocol(entry.protocol),
                name=f"{entry.protocol}:{entry.port_from}-{entry.port_to}",
                protocol=entry.protocol,
                port_from=entry.port_from,
                port_to=entry.port_to,
            )

    if proto in {"icmp", "icmp6"}:
        icmp_type = _ICMP_NAME_TO_TYPE.get(ref.lower().replace(" ", "-"))
        key = f"service:{proto}:icmp-{ref}"
        return CanonicalObject.create(
            canonical_snapshot_id=canonical_snapshot_id,
            object_key=key,
            object_family=ObjectFamily.SERVICE,
            object_kind=ObjectKind.ICMP,
            name=ref,
            protocol=proto,
            icmp_type=icmp_type,
        )

    return None


def build_ip_protocol_service(
    *,
    canonical_snapshot_id: UUID,
    protocol_number: int | None = None,
    protocol_name: str | None = None,
) -> CanonicalObject:
    """Build an IP-level protocol service object (numeric or named).

    Used for ACL operands with ProtocolOperandKind.IP_PROTOCOL_NUMBER and
    implicit protocol ip rules in normalizer/services.py. Also used as
    fallback in materialize_protocol_object_member when payload building
    returns None.

    Keys come from ip_protocol_object_key (e.g. service:ip, service:6).
    """
    if protocol_number is not None:
        proto = str(protocol_number)
        key = ip_protocol_object_key(proto)
        name = f"ip-proto-{proto}"
    else:
        proto = (protocol_name or "ip").lower()
        key = ip_protocol_object_key(proto)
        name = proto

    return CanonicalObject.create(
        canonical_snapshot_id=canonical_snapshot_id,
        object_key=key,
        object_family=ObjectFamily.SERVICE,
        object_kind=ObjectKind.IP_PROTO,
        name=name,
        protocol=proto,
        description="ASA IP protocol operand",
    )


def parse_port_object_line(raw: str, default_protocol: str | None) -> dict | None:
    """Parse a service-group port-object line into a service payload dict.

    Called from materialize_service_group_member when expanding group body
    members. default_protocol is inherited from the enclosing service-group
    header (often tcp).

    Supports eq and range forms. Non-numeric eq operands may resolve
    through lookup_builtin_service before giving up.

    Returns:
        Payload dict suitable for build_canonical_service_from_payload, or
        None when the line cannot be parsed (member becomes unresolved).
    """
    parts = raw.split()
    if not parts:
        return None
    lowered = [p.lower() for p in parts]
    proto = (default_protocol or "tcp").lower()

    if "eq" in lowered:
        idx = lowered.index("eq")
        if idx + 1 >= len(parts):
            return None
        port_tok = parts[idx + 1]
        port = parse_port_token(port_tok)
        if port is None:
            entry = lookup_builtin_service(port_tok, protocol_hint=proto)
            if entry is None:
                return None
            return {
                "protocol": entry.protocol,
                "op": "eq",
                "port": str(entry.port_from),
            }
        return {"protocol": proto, "op": "eq", "port": str(port)}

    if "range" in lowered:
        idx = lowered.index("range")
        if idx + 2 >= len(parts):
            return None
        return {
            "protocol": proto,
            "op": "range",
            "port_from": parts[idx + 1],
            "port_to": parts[idx + 2],
        }

    return None


def canonical_object_for_parsed_service(
    *,
    canonical_snapshot_id: UUID,
    svc_item: ParsedServiceObject,
) -> CanonicalObject:
    """Build canonical header object for one parsed service entity.

    Entry point for _materialize_service_objects in normalizer/services.py.
    Always returns an object (never None):

    - service/protocol groups -> ObjectKind.SERVICE_GROUP header at
      service:{name}
    - leaf service objects -> via build_canonical_service_from_payload
    - unsupported leaf payload -> generic IP_PROTO stub preserving name/key
      so normalization continues (member edges may still fail separately)
    """
    key = f"service:{svc_item.name}"
    if svc_item.kind.value == "service_group":
        return CanonicalObject.create(
            canonical_snapshot_id=canonical_snapshot_id,
            object_key=key,
            object_family=ObjectFamily.SERVICE,
            object_kind=ObjectKind.SERVICE_GROUP,
            name=svc_item.name,
            protocol=(svc_item.payload.get("protocol") or None),
            description=svc_item.payload.get("description"),
        )

    if svc_item.kind.value == "protocol_group":
        return CanonicalObject.create(
            canonical_snapshot_id=canonical_snapshot_id,
            object_key=key,
            object_family=ObjectFamily.SERVICE,
            object_kind=ObjectKind.SERVICE_GROUP,
            name=svc_item.name,
            protocol="protocol-group",
            description=svc_item.payload.get("description"),
        )

    built = build_canonical_service_from_payload(
        canonical_snapshot_id=canonical_snapshot_id,
        name=svc_item.name,
        object_key=key,
        payload=svc_item.payload,
    )
    if built is not None:
        return built

    return CanonicalObject.create(
        canonical_snapshot_id=canonical_snapshot_id,
        object_key=key,
        object_family=ObjectFamily.SERVICE,
        object_kind=ObjectKind.IP_PROTO,
        name=svc_item.name,
        description=svc_item.payload.get("description"),
    )
