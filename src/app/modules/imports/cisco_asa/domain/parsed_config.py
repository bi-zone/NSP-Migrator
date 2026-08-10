from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.modules.imports.cisco_asa.domain.enums import (
    AclUsageType,
    ProtocolOperandKind,
)


class ParsedObjectType(StrEnum):
    """Discriminator for address/service entries in parsed object lists."""

    ADDRESS = "address"
    ADDRESS_GROUP = "address_group"
    SERVICE = "service"
    SERVICE_GROUP = "service_group"
    PROTOCOL_GROUP = "protocol_group"


@dataclass(slots=True)
class ParsedAddressObject:
    """One parsed object network or object-group network header.

    payload holds vendor-specific body fields (type, ip, mask,
    members, …) consumed by _addr_object_from_payload and group member
    wiring in the address normalizer mixin.
    """

    name: str
    kind: ParsedObjectType
    payload: dict
    source_line: int


@dataclass(slots=True)
class ParsedServiceObject:
    """One parsed service, service-group, icmp-type, or protocol-group header.

    Protocol groups are stored in ParsedConfig.service_objects alongside
    service groups (see ProtocolGroupExtractor). payload includes
    members, protocol, group_kind, etc. for builders.py and
    members.py.
    """

    name: str
    kind: ParsedObjectType
    payload: dict
    source_line: int


@dataclass(slots=True)
class CryptoMapLink:
    """Crypto map entry referencing an ACL by name.

    Populated on ParsedConfig.crypto_map_links from AsaIndex for usage
    classification context. Not directly materialized as canonical entities.
    """

    map_name: str
    sequence: int
    acl_name: str
    source_line: int


class AclBindingType(StrEnum):
    """How an ACL is bound in ASA config (from ZoneResolver)."""

    INTERFACE = "interface"
    GLOBAL = "global"
    UNKNOWN = "unknown"


class ZoneInferenceStatus(StrEnum):
    """Whether directional src/dst zones could be inferred for a rule."""

    DIRECTIONAL = "directional"
    NON_DIRECTIONAL = "non_directional"
    GLOBAL_SCOPE = "global_scope"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class ParsedAccessRule:
    """One extended ACL rule after parsing (may fan out per binding context).

    ExtendedAclExtractor may emit **multiple** ParsedAccessRule rows for
    the same access-list line when ZoneResolver returns several binding
    contexts (e.g. ACL applied on multiple interfaces).

    Normalizer reads virtually all fields: operands from src_ref/dst_ref/
    service_ref, zones from src_zone/dst_zone, issues from
    zone_inference_status/acl_usage_type, metadata from
    binding_context_key and raw_line_text.

    Attributes:
        rule_name: Stable parser key {acl_name}:{order} — input to
            DeterministicRuleKeyBuilder (may gain :dupN suffix).
        src_ref/dst_ref: Normalized operand tokens (any, host:…,
            net:…, object name, object-group name).
        service_ref: Port/object tail after protocol parsing, or None.
        unresolved_zone: True when interface-bound zones could not be inferred.
        binding_context_key: Dedup scope for textual duplicates and metadata
            (e.g. global, interface:outside:in).
    """

    acl_name: str
    rule_name: str
    action: str
    protocol: str
    src_ref: str
    dst_ref: str
    service_ref: str | None
    enabled: bool
    order: int
    line_start: int
    line_end: int
    src_zone: str | None
    dst_zone: str | None
    unresolved_zone: bool
    acl_binding_type: AclBindingType = AclBindingType.UNKNOWN
    zone_inference_status: ZoneInferenceStatus = ZoneInferenceStatus.UNKNOWN
    time_range: str | None = None
    log: bool = False
    protocol_operand_kind: ProtocolOperandKind = ProtocolOperandKind.LITERAL
    protocol_group_ref: str | None = None
    protocol_number: int | None = None
    acl_usage_type: AclUsageType = AclUsageType.UNKNOWN
    crypto_map_name: str | None = None
    crypto_map_seq: int | None = None
    raw_line_text: str = ""
    binding_context_key: str = "unbound"
    binding_interface: str | None = None
    binding_direction: str | None = None


@dataclass(slots=True)
class ParsedConfig:
    """Root aggregate produced by CiscoAsaParserAdapter.parse.

    Lists are consumed sequentially by the normalizer orchestrator:
    address objects -> address group members -> service objects -> service/protocol
    group members -> rules.

    Attributes:
        address_objects: Network objects and groups from AddressExtractor.
        service_objects: Service groups, leaf services, and protocol groups.
        rules: Extended ACL rules from ExtendedAclExtractor.
        crypto_map_links: ACL - crypto-map references for usage classification.
    """

    address_objects: list[ParsedAddressObject] = field(default_factory=list)
    service_objects: list[ParsedServiceObject] = field(default_factory=list)
    rules: list[ParsedAccessRule] = field(default_factory=list)
    crypto_map_links: list[CryptoMapLink] = field(default_factory=list)