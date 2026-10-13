import pytest

from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanAddrObjectType,
    SdwanServiceL4Proto,
)
from app.modules.mapping.domain.value_objects import (
    CreateAddrObjectPayload,
    CreateServicePayload,
)


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        (
            CreateAddrObjectPayload(
                type=SdwanAddrObjectType.PREFIX,
                prefix="192.0.2.0/24",
            ),
            SdwanAddrObjectType.PREFIX,
        ),
        (
            CreateAddrObjectPayload(
                type=SdwanAddrObjectType.HOST,
                host="192.0.2.10",
            ),
            SdwanAddrObjectType.HOST,
        ),
        (
            CreateAddrObjectPayload(
                type=SdwanAddrObjectType.FQDN,
                fqdn="example.test",
            ),
            SdwanAddrObjectType.FQDN,
        ),
        (
            CreateAddrObjectPayload(
                type=SdwanAddrObjectType.IP_RANGE,
                ip_range_from="192.0.2.10",
                ip_range_to="192.0.2.20",
            ),
            SdwanAddrObjectType.IP_RANGE,
        ),
    ],
)
def test_create_addr_object_payload_accepts_required_value(
    payload: CreateAddrObjectPayload,
    expected_type: SdwanAddrObjectType,
) -> None:
    assert payload.type == expected_type


@pytest.mark.parametrize(
    ("object_type", "kwargs", "message"),
    [
        (SdwanAddrObjectType.PREFIX, {}, "Prefix"),
        (SdwanAddrObjectType.HOST, {}, "Host"),
        (SdwanAddrObjectType.FQDN, {}, "FQDN"),
        (SdwanAddrObjectType.IP_RANGE, {}, "IP Range"),
    ],
)
def test_create_addr_object_payload_requires_value_for_type(
    object_type: SdwanAddrObjectType,
    kwargs: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        CreateAddrObjectPayload(type=object_type, **kwargs)


@pytest.mark.parametrize(
    "payload",
    [
        CreateServicePayload(
            name="https",
            l4_proto=SdwanServiceL4Proto.TCP,
            port_start=443,
            port_end=443,
        ),
        CreateServicePayload(
            name="dns",
            l4_proto=SdwanServiceL4Proto.UDP,
            port_start=53,
            port_end=53,
        ),
        CreateServicePayload(
            name="echo-request",
            l4_proto=SdwanServiceL4Proto.ICMP,
            icmp_codes=["echo_request"],
        ),
    ],
)
def test_create_service_payload_accepts_supported_complete_signature(
    payload: CreateServicePayload,
) -> None:
    assert payload.name


@pytest.mark.parametrize(
    ("proto", "kwargs", "message"),
    [
        (SdwanServiceL4Proto.TCP, {}, "TCP/UDP"),
        (SdwanServiceL4Proto.UDP, {"port_start": 53}, "TCP/UDP"),
        (SdwanServiceL4Proto.ICMP, {}, "ICMP"),
    ],
)
def test_create_service_payload_rejects_incomplete_signature(
    proto: SdwanServiceL4Proto,
    kwargs: dict[str, int],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        CreateServicePayload(name="incomplete", l4_proto=proto, **kwargs)
