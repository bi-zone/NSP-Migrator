"""Service object materialization helpers package."""

from app.modules.imports.cisco_asa.adapters.services.facade import (
    build_canonical_service_from_payload,
    build_inline_service_from_ref,
    build_ip_protocol_service,
    canonical_object_for_parsed_service,
    ip_protocol_object_key,
    materialize_protocol_object_member,
    materialize_service_group_member,
    parse_port_object_line,
    service_object_key,
)

__all__ = [
    "build_canonical_service_from_payload",
    "build_inline_service_from_ref",
    "build_ip_protocol_service",
    "canonical_object_for_parsed_service",
    "ip_protocol_object_key",
    "materialize_protocol_object_member",
    "materialize_service_group_member",
    "parse_port_object_line",
    "service_object_key",
]
