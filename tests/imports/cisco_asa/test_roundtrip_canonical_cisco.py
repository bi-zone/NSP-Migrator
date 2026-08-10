"""Roundtrip regression: canonical -> ASA text -> canonical."""

from __future__ import annotations

from ipaddress import IPv4Network
from uuid import uuid4

from app.modules.canonical.domain.enums import ObjectKind, OperandRole
from app.modules.imports.cisco_asa.adapters.normalizer import CiscoAsaNormalizerAdapter
from app.modules.imports.cisco_asa.adapters.parser import CiscoAsaParserAdapter

SOURCE_CFG = """
access-list ACL_OUT extended permit tcp any host 10.0.0.10 eq 443
access-list ACL_OUT extended deny tcp any any eq 22
access-group ACL_OUT in interface outside
interface outside
 nameif outside
"""


def _normalize(raw_cfg: str):
    parsed = CiscoAsaParserAdapter().parse(raw_cfg)
    return CiscoAsaNormalizerAdapter().normalize(parsed, source_snapshot_id=uuid4())


def _parse_binding_context(description: str | None) -> str:
    if not description:
        return "unbound"
    for chunk in description.split(";"):
        chunk = chunk.strip()
        if chunk.startswith("binding_context="):
            return chunk.split("=", 1)[1]
    return "unbound"


def _object_fingerprint(obj) -> str:  # noqa: ANN001
    if obj.object_kind == ObjectKind.ANY_ADDR:
        return "addr:any"
    if obj.object_kind == ObjectKind.HOST:
        return f"addr:host:{obj.cidr or obj.name}"
    if obj.object_kind == ObjectKind.SUBNET:
        return f"addr:subnet:{obj.cidr}"
    if obj.object_kind == ObjectKind.TCP:
        return f"svc:tcp:{obj.port_from}-{obj.port_to}"
    if obj.object_kind == ObjectKind.UDP:
        return f"svc:udp:{obj.port_from}-{obj.port_to}"
    if obj.object_kind == ObjectKind.ICMP:
        return f"svc:icmp:{obj.icmp_type}:{obj.icmp_code}"
    if obj.object_kind == ObjectKind.IP_PROTO:
        return f"svc:ipproto:{obj.protocol}"
    if obj.object_kind in {ObjectKind.SERVICE_GROUP, ObjectKind.ADDR_GROUP}:
        return f"group:{obj.object_key}"
    return f"obj:{obj.object_key}"


def _canonical_rule_signatures(outcome) -> list[tuple]:  # noqa: ANN001
    objects_by_id = {obj.id: obj for obj in outcome.canonical.objects}
    operands_by_rule: dict = {}
    for operand in outcome.canonical.operands:
        operands_by_rule.setdefault(operand.rule_id, []).append(operand)

    signatures: list[tuple] = []
    for rule in outcome.canonical.rules:
        rule_ops = operands_by_rule.get(rule.id, [])
        by_role = {
            op.operand_role: objects_by_id.get(op.target_object_id)
            for op in rule_ops
            if op.target_object_id is not None
        }
        service_obj = by_role.get(OperandRole.SERVICE)
        signatures.append(
            (
                rule.section,
                rule.action,
                rule.enabled,
                rule.priority,
                _parse_binding_context(rule.description),
                _object_fingerprint(by_role[OperandRole.SRC_OBJECT]),
                _object_fingerprint(by_role[OperandRole.DST_OBJECT]),
                _object_fingerprint(service_obj) if service_obj else "svc:none",
            )
        )
    return sorted(signatures)


def _addr_object_to_asa(obj) -> str:  # noqa: ANN001
    if obj.object_kind == ObjectKind.ANY_ADDR:
        return "any"
    if obj.object_kind == ObjectKind.HOST:
        ip = (obj.cidr or "").split("/", 1)[0]
        return f"host {ip}"
    if obj.object_kind == ObjectKind.SUBNET and obj.cidr:
        network = IPv4Network(obj.cidr, strict=False)
        return f"{network.network_address} {network.netmask}"
    return "any"


def _service_to_proto_and_clause(service_obj) -> tuple[str, str]:  # noqa: ANN001
    if service_obj is None:
        return "ip", ""
    if service_obj.object_kind == ObjectKind.TCP:
        if service_obj.port_from == service_obj.port_to:
            return "tcp", f" eq {service_obj.port_from}"
        return "tcp", f" range {service_obj.port_from} {service_obj.port_to}"
    if service_obj.object_kind == ObjectKind.UDP:
        if service_obj.port_from == service_obj.port_to:
            return "udp", f" eq {service_obj.port_from}"
        return "udp", f" range {service_obj.port_from} {service_obj.port_to}"
    if service_obj.object_kind == ObjectKind.IP_PROTO:
        proto = service_obj.protocol or "ip"
        return proto, ""
    if service_obj.object_kind == ObjectKind.ICMP:
        return "icmp", ""
    return "ip", ""


def _render_asa_from_canonical(outcome) -> str:  # noqa: ANN001
    objects_by_id = {obj.id: obj for obj in outcome.canonical.objects}
    operands_by_rule: dict = {}
    for operand in outcome.canonical.operands:
        operands_by_rule.setdefault(operand.rule_id, []).append(operand)

    access_groups: set[str] = set()
    interfaces: set[str] = set()
    lines: list[str] = []

    for rule in sorted(outcome.canonical.rules, key=lambda item: item.priority):
        ops = operands_by_rule.get(rule.id, [])
        by_role = {
            op.operand_role: objects_by_id.get(op.target_object_id)
            for op in ops
            if op.target_object_id is not None
        }
        src = _addr_object_to_asa(by_role[OperandRole.SRC_OBJECT])
        dst = _addr_object_to_asa(by_role[OperandRole.DST_OBJECT])
        proto, svc_clause = _service_to_proto_and_clause(by_role.get(OperandRole.SERVICE))
        lines.append(
            f"access-list {rule.section} extended {rule.action.lower()} {proto} {src} {dst}{svc_clause}"
        )

        binding = _parse_binding_context(rule.description)
        if binding.startswith("interface:"):
            _, iface, direction = binding.split(":", 2)
            access_groups.add(f"access-group {rule.section} {direction} interface {iface}")
            interfaces.add(iface)
        elif binding == "global":
            access_groups.add(f"access-group {rule.section} global")

    for iface in sorted(interfaces):
        lines.append(f"interface {iface}")
        lines.append(f" nameif {iface}")
    lines.extend(sorted(access_groups))
    return "\n".join(lines) + "\n"


def test_canonical_to_cisco_and_back_preserves_rule_semantics():
    first = _normalize(SOURCE_CFG)
    asa_from_canonical = _render_asa_from_canonical(first)
    second = _normalize(asa_from_canonical)

    assert _canonical_rule_signatures(first) == _canonical_rule_signatures(second)
    assert {issue.issue_code for issue in first.canonical.issues} == {
        issue.issue_code for issue in second.canonical.issues
    }
