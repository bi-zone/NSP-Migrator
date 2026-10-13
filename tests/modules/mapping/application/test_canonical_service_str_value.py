from uuid import uuid4

from app.modules.mapping.application.get_mapping_scope_rules_projection import (
    _MappingScopeRulesProjectionBuilder,
)
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalService,
    CanonicalServiceKind,
)


def _service(
    *,
    kind: CanonicalServiceKind = CanonicalServiceKind.TCP,
    protocol: str | None = "tcp",
    port_from: int | None = None,
    port_to: int | None = None,
    name: str = "svc",
) -> CanonicalService:
    return CanonicalService(
        id=uuid4(),
        kind=kind,
        name=name,
        protocol=protocol,
        port_from=port_from,
        port_to=port_to,
    )


def test_canonical_tcp_identical_ports_collapse_in_str_value() -> None:
    value = _MappingScopeRulesProjectionBuilder._canonical_service_str_value(
        _service(port_from=22, port_to=22)
    )
    assert value == "tcp/22"


def test_canonical_udp_real_range_keeps_from_to() -> None:
    value = _MappingScopeRulesProjectionBuilder._canonical_service_str_value(
        _service(
            kind=CanonicalServiceKind.UDP,
            protocol="udp",
            port_from=1000,
            port_to=2000,
        )
    )
    assert value == "udp/1000-2000"
