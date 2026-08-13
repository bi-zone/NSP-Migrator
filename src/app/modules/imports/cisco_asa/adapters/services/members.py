from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from app.modules.canonical.domain import CanonicalObject, ObjectFamily, ObjectKind
from app.modules.imports.cisco_asa.adapters.normalizer.state import _ObjectRef
from app.modules.imports.cisco_asa.adapters.services.builders import (
    build_canonical_service_from_payload,
    build_ip_protocol_service,
    parse_port_object_line,
    resolve_l4_destination_range,
)
from app.modules.imports.cisco_asa.adapters.services.common import (
    _ICMP_NAME_TO_TYPE,
    ip_protocol_object_key,
    service_object_key,
)
from app.modules.imports.cisco_asa.parsing.service_catalog import parse_port_token
from app.modules.imports.cisco_asa.parsing.service_members import (
    parse_inline_service_object,
)


def _register_service_payload(
    payload: dict,
    *,
    canonical_snapshot_id: UUID,
    objects_by_key: dict[str, _ObjectRef],
    register: Callable[[CanonicalObject], CanonicalObject],
) -> str | None:
    """Derive object key from payload, register leaf service if missing.

    Internal helper for service-object members inside
    materialize_service_group_member. Key derivation mirrors ASA service
    shapes (tcp/udp eq/range, tcp-udp, icmp, ip-level protocols).

    Side Effects:
        May call register once when obj_key is not yet in
        objects_by_key.

    Returns:
        Canonical object key string, or None when payload is unsupported.
    """
    proto = (payload.get("protocol") or "").lower()
    if not proto:
        return None

    if proto in {"tcp", "udp"}:
        port_range = resolve_l4_destination_range(payload)
        if port_range is None:
            return None
        obj_key = service_object_key(proto, port_range[0], port_range[1])
    elif (
        proto == "tcp-udp"
        and payload.get("op") == "eq"
        and payload.get("port") is not None
    ):
        port = parse_port_token(str(payload["port"]))
        if port is None:
            return None
        obj_key = f"service:tcp-udp:{port}-{port}"
    elif proto in {"icmp", "icmp6"}:
        icmp = (payload.get("icmp") or "any").lower().replace(" ", "-")
        obj_key = f"service:{proto}:icmp-{icmp}"
    elif proto.isdigit() or proto in {"ip", "esp", "ah", "gre"}:
        obj_key = ip_protocol_object_key(proto)
    else:
        return None

    if obj_key not in objects_by_key:
        built = build_canonical_service_from_payload(
            canonical_snapshot_id=canonical_snapshot_id,
            name=obj_key.removeprefix("service:"),
            object_key=obj_key,
            payload=payload,
        )
        if built is None:
            return None
        register(built)
    return obj_key


def materialize_protocol_object_member(
    raw: str,
    *,
    canonical_snapshot_id: UUID,
    objects_by_key: dict[str, _ObjectRef],
    register: Callable[[CanonicalObject], CanonicalObject],
) -> str | None:
    """Materialize one protocol-object line from a protocol object-group.

    Used for type=protocol-object members and indirectly from
    materialize_service_group_member. Registers an IP-protocol service at
    ip_protocol_object_key(proto) when absent.

    Side Effects:
        May register a new canonical object via register.
    """
    proto = raw.strip().lower()
    if not proto:
        return None

    payload = {"protocol": proto}
    obj_key = ip_protocol_object_key(proto)
    if obj_key not in objects_by_key:
        built = build_canonical_service_from_payload(
            canonical_snapshot_id=canonical_snapshot_id,
            name=obj_key.removeprefix("service:"),
            object_key=obj_key,
            payload=payload,
        )
        if built is None:
            built = build_ip_protocol_service(
                canonical_snapshot_id=canonical_snapshot_id,
                protocol_name=proto,
            )
        register(built)
    return obj_key


def materialize_service_group_member(  # noqa: C901
    member: dict,
    *,
    canonical_snapshot_id: UUID,
    group_protocol: str | None,
    objects_by_key: dict[str, _ObjectRef],
    register: Callable[[CanonicalObject], CanonicalObject],
) -> list[str]:
    """Resolve one parsed group member to canonical child object key(s).

    Primary entry from _attach_group_members. Return semantics:

    - non-empty list -> member resolved; keys may reference pre-existing or newly
      registered objects
    - empty list -> member unresolved; normalizer emits
      unresolved_group_member_ref

    group_protocol is inherited from the service-group header and passed to
    parse_port_object_line for port-object members (see
    test_service_group_members_persisted_as_object_members).

    Side Effects:
        May register leaf services for inline port-object, icmp-object,
        service-object, and protocol-object members.
    """
    mtype = (member.get("type") or "").lower()
    if mtype == "service-object-object" and member.get("name"):
        key = f"service:{member['name']}"
        return [key] if key in objects_by_key else []

    if mtype == "group-object" and member.get("name"):
        key = f"service:{member['name']}"
        return [key] if key in objects_by_key else []

    if mtype == "icmp-object" and member.get("name"):
        icmp_name = str(member["name"])
        key = f"service:icmp:{icmp_name}"
        if key not in objects_by_key:
            icmp_type = _ICMP_NAME_TO_TYPE.get(icmp_name.lower().replace(" ", "-"))
            obj = CanonicalObject.create(
                canonical_snapshot_id=canonical_snapshot_id,
                object_key=key,
                object_family=ObjectFamily.SERVICE,
                object_kind=ObjectKind.ICMP,
                name=icmp_name,
                protocol="icmp",
                icmp_type=icmp_type,
            )
            register(obj)
        return [key]

    if mtype == "port-object" and member.get("raw"):
        raw = str(member["raw"])
        parsed = parse_port_object_line(raw, group_protocol)
        if parsed is None:
            return []
        proto = parsed["protocol"]
        if parsed.get("op") == "eq":
            port = int(parsed["port"])
            p_from = port
            p_to = port
        else:
            p_from = parse_port_token(str(parsed["port_from"]))  # type: ignore
            p_to = parse_port_token(str(parsed["port_to"]))  # type: ignore
            if p_from is None or p_to is None:
                return []

        protocols = ("tcp", "udp") if proto == "tcp-udp" else (proto,)
        child_keys: list[str] = []
        for child_protocol in protocols:
            obj_key = service_object_key(child_protocol, p_from, p_to)
            if obj_key not in objects_by_key:
                built = build_canonical_service_from_payload(
                    canonical_snapshot_id=canonical_snapshot_id,
                    name=obj_key.removeprefix("service:"),
                    object_key=obj_key,
                    payload={**parsed, "protocol": child_protocol},
                )
                if built is None:
                    return []
                register(built)
            child_keys.append(obj_key)
        return child_keys

    if mtype == "service-object":
        payload = member.get("payload")
        if isinstance(payload, dict):
            payload_key = _register_service_payload(
                payload,
                canonical_snapshot_id=canonical_snapshot_id,
                objects_by_key=objects_by_key,
                register=register,
            )
            return [payload_key] if payload_key else []

        raw_member = member.get("raw")
        if raw_member:
            parsed_inline = parse_inline_service_object(str(raw_member))
            if parsed_inline:
                inline_key = _register_service_payload(
                    parsed_inline,
                    canonical_snapshot_id=canonical_snapshot_id,
                    objects_by_key=objects_by_key,
                    register=register,
                )
                return [inline_key] if inline_key else []
        return []

    if mtype == "protocol-object" and member.get("raw"):
        protocol_key = materialize_protocol_object_member(
            str(member["raw"]),
            canonical_snapshot_id=canonical_snapshot_id,
            objects_by_key=objects_by_key,
            register=register,
        )
        return [protocol_key] if protocol_key else []

    return []
