from app.modules.imports.cisco_asa.adapters.services.common import (
    service_object_key,
    service_port_label,
    service_port_range_label,
)


def test_identical_bounds_collapse_to_single_port() -> None:
    assert service_port_range_label(22, 22) == "22"
    assert service_port_label("tcp", 22, 22) == "tcp:22"
    assert service_object_key("tcp", 22, 22) == "service:tcp:22"
    assert service_object_key("udp", 53, 53) == "service:udp:53"
    assert service_object_key("tcp-udp", 80, 80) == "service:tcp-udp:80"


def test_real_ranges_keep_from_to() -> None:
    assert service_port_range_label(1000, 2000) == "1000-2000"
    assert service_port_label("tcp", 1000, 2000) == "tcp:1000-2000"
    assert service_object_key("tcp", 1000, 2000) == "service:tcp:1000-2000"
    assert service_object_key("udp", 5000, 5001) == "service:udp:5000-5001"
