from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ServiceCatalogEntry:
    protocol: str
    port_from: int
    port_to: int


# TODO:: аналогично разобраться как будем хранить альясы
_BUILTIN_SERVICES: dict[str, ServiceCatalogEntry] = {
    "bootps": ServiceCatalogEntry("udp", 67, 67),
    "bootpc": ServiceCatalogEntry("udp", 68, 68),
    "echo": ServiceCatalogEntry("tcp", 7, 7),
    "ftp-data": ServiceCatalogEntry("tcp", 20, 20),
    "www": ServiceCatalogEntry("tcp", 80, 80),
    "http": ServiceCatalogEntry("tcp", 80, 80),
    "https": ServiceCatalogEntry("tcp", 443, 443),
    "ssh": ServiceCatalogEntry("tcp", 22, 22),
    "telnet": ServiceCatalogEntry("tcp", 23, 23),
    "rsh": ServiceCatalogEntry("tcp", 514, 514),
    "lpd": ServiceCatalogEntry("tcp", 515, 515),
    "smtp": ServiceCatalogEntry("tcp", 25, 25),
    "domain": ServiceCatalogEntry("udp", 53, 53),
    "dns": ServiceCatalogEntry("udp", 53, 53),
    "ntp": ServiceCatalogEntry("udp", 123, 123),
    "snmp": ServiceCatalogEntry("udp", 161, 161),
    "snmptrap": ServiceCatalogEntry("udp", 162, 162),
    "syslog": ServiceCatalogEntry("udp", 514, 514),
    "sunrpc": ServiceCatalogEntry("tcp", 111, 111),
    "nfs": ServiceCatalogEntry("tcp", 2049, 2049),
    "radius": ServiceCatalogEntry("udp", 1812, 1812),
    "radius-acct": ServiceCatalogEntry("udp", 1813, 1813),
    "rtsp": ServiceCatalogEntry("tcp", 554, 554),
    "netbios-ssn": ServiceCatalogEntry("tcp", 139, 139),
    "tftp": ServiceCatalogEntry("udp", 69, 69),
    "ftp": ServiceCatalogEntry("tcp", 21, 21),
    "pop3": ServiceCatalogEntry("tcp", 110, 110),
    "imap4": ServiceCatalogEntry("tcp", 143, 143),
    "imap": ServiceCatalogEntry("tcp", 143, 143),
    "ldap": ServiceCatalogEntry("tcp", 389, 389),
    "ldaps": ServiceCatalogEntry("tcp", 636, 636),
    "rdp": ServiceCatalogEntry("tcp", 3389, 3389),
    "ms-sql": ServiceCatalogEntry("tcp", 1433, 1433),
    "mssql": ServiceCatalogEntry("tcp", 1433, 1433),
    "mysql": ServiceCatalogEntry("tcp", 3306, 3306),
    "postgresql": ServiceCatalogEntry("tcp", 5432, 5432),
    "postgres": ServiceCatalogEntry("tcp", 5432, 5432),
}


def lookup_builtin_service(
    name: str,
    *,
    protocol_hint: str | None = None,
) -> ServiceCatalogEntry | None:
    key = name.strip().lower()
    entry = _BUILTIN_SERVICES.get(key)
    if entry is None:
        return None
    if protocol_hint and protocol_hint.lower() in {"tcp", "udp"}:
        hinted = protocol_hint.lower()
        if entry.protocol != hinted and key in {"domain", "dns", "ntp", "snmp", "tftp"}:
            return entry
        return ServiceCatalogEntry(hinted, entry.port_from, entry.port_to)
    return entry


def parse_port_token(token: str) -> int | None:
    token = token.strip()
    if token.isdigit():
        return int(token)
    entry = lookup_builtin_service(token)
    if entry is not None:
        return entry.port_from
    return None
