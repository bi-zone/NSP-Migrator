from __future__ import annotations

from app.modules.canonical.domain import ObjectKind

_ICMP_NAME_TO_TYPE: dict[str, int] = {
    "echo": 8,
    "echo-reply": 0,
    "alternate-address": 6,
    "destination-unreachable": 3,
    "source-quench": 4,
    "redirect": 5,
    "router-advertisement": 9,
    "router-solicitation": 10,
    "time-exceeded": 11,
    "parameter-problem": 12,
    "timestamp-request": 13,
    "timestamp-reply": 14,
    "information-request": 15,
    "information-reply": 16,
    "mask-request": 17,
    "mask-reply": 18,
    "traceroute": 30,
}


def kind_for_protocol(proto: str) -> ObjectKind:
    p = proto.lower()
    if p == "tcp":
        return ObjectKind.TCP
    if p == "udp":
        return ObjectKind.UDP
    if p in {"icmp", "icmp6"}:
        return ObjectKind.ICMP
    if p in {"ip", "esp", "ah", "gre"}:
        return ObjectKind.IP_PROTO
    return ObjectKind.IP_PROTO


def service_object_key(protocol: str, port_from: int, port_to: int) -> str:
    return f"service:{protocol}:{port_from}-{port_to}"


def ip_protocol_object_key(protocol: str) -> str:
    return f"service:ip-proto:{protocol.lower()}"
