import pytest

from app.integrations.sdwan_csp_api.gateways.enums import SdwanServiceL4Proto
from app.modules.execute.services.rule_values_resolver import (
    AddressSpan,
    FqdnValue,
    RuleValueNormalizationError,
    ServiceValue,
)


def test_address_span_normalizes_network_host_and_range_for_coverage() -> None:
    subnet = AddressSpan.from_network("192.0.2.0/24")

    assert subnet.covers(AddressSpan.from_host("192.0.2.10"))
    assert subnet.covers(AddressSpan.from_range("192.0.2.10", "192.0.2.20"))
    assert subnet.display() == "192.0.2.0-192.0.2.255"


def test_address_span_rejects_reversed_range() -> None:
    with pytest.raises(RuleValueNormalizationError, match="start .* greater"):
        AddressSpan.from_range("192.0.2.20", "192.0.2.10")


def test_fqdn_value_compares_normalized_name_only() -> None:
    fqdn = FqdnValue.from_raw(" Example.TEST ")

    assert fqdn.covers(FqdnValue.from_raw("example.test"))
    assert not fqdn.covers(AddressSpan.from_host("192.0.2.10"))
    assert fqdn.display() == "example.test"


def test_any_service_covers_every_protocol_but_not_vice_versa() -> None:
    any_service = ServiceValue.any()
    tcp = ServiceValue.port_range(SdwanServiceL4Proto.TCP, 443, 443)

    assert any_service.covers(tcp)
    assert not tcp.covers(any_service)


def test_tcp_port_range_covers_only_range_of_same_protocol() -> None:
    existing = ServiceValue.port_range(SdwanServiceL4Proto.TCP, 1, 1024)

    assert existing.covers(ServiceValue.port_range(SdwanServiceL4Proto.TCP, 443, 443))
    assert not existing.covers(
        ServiceValue.port_range(SdwanServiceL4Proto.UDP, 443, 443)
    )


@pytest.mark.parametrize(
    ("start", "end"),
    [(-1, 80), (443, 65536), (1024, 443)],
)
def test_tcp_udp_port_ranges_reject_invalid_boundaries(start: int, end: int) -> None:
    with pytest.raises(RuleValueNormalizationError, match="Invalid port range"):
        ServiceValue.port_range(SdwanServiceL4Proto.TCP, start, end)


def test_icmp_code_coverage_uses_normalized_set_membership() -> None:
    existing = ServiceValue.icmp([" Echo_Request ", "destination-unreachable"])
    planned = ServiceValue.icmp(["echo-request"])

    assert existing.covers(planned)
    assert not planned.covers(existing)
    assert existing.display() == "icmp/destination-unreachable,echo-request"


def test_ip_ip_is_only_covered_by_the_same_protocol_only_service() -> None:
    ip_ip = ServiceValue.protocol_only(SdwanServiceL4Proto.IP_IP)

    assert ip_ip.covers(ServiceValue.protocol_only(SdwanServiceL4Proto.IP_IP))
    assert not ip_ip.covers(ServiceValue.port_range(SdwanServiceL4Proto.TCP, 80, 80))
