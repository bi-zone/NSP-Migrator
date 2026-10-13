from ipaddress import IPv4Address

import pytest

from app.integrations.sdwan_csp_api.gateways.address_group_resolver import (
    SDWANAddressGroupLeavesResolver,
    SDWANAddressGroupResolutionError,
)
from app.integrations.sdwan_csp_api.gateways.enums import SdwanAddrObjectType
from app.integrations.sdwan_csp_api.gateways.models import SdwanAddrObject


def _group(
    object_id: int,
    group_id: int,
    *,
    parents: tuple[int, ...] = (),
) -> SdwanAddrObject:
    return SdwanAddrObject(
        id=object_id,
        parents=parents,
        name=f"group-{object_id}",
        type=SdwanAddrObjectType.ADDR_GROUP,
        addr_group=group_id,
    )


def _host(
    object_id: int,
    value: str,
    *,
    parents: tuple[int, ...] = (),
) -> SdwanAddrObject:
    return SdwanAddrObject(
        id=object_id,
        parents=parents,
        name=f"host-{object_id}",
        type=SdwanAddrObjectType.HOST,
        host=IPv4Address(value),
    )


def test_resolve_leaves_expands_nested_group_in_catalog_order() -> None:
    resolver = SDWANAddressGroupLeavesResolver(
        [
            _group(10, group_id=100),
            _host(11, "10.0.0.11", parents=(100,)),
            _group(12, group_id=120, parents=(100,)),
            _host(13, "10.0.0.13", parents=(120,)),
            _host(14, "10.0.0.14"),
        ]
    )

    leaves = resolver.resolve_leaves(10)

    assert [leaf.id for leaf in leaves] == [11, 13]
    assert resolver.resolve_leaves(14) == (_host(14, "10.0.0.14"),)


def test_resolve_leaves_rejects_unknown_object_and_empty_group() -> None:
    resolver = SDWANAddressGroupLeavesResolver([_group(10, group_id=100)])

    with pytest.raises(SDWANAddressGroupResolutionError, match="Unknown address"):
        resolver.resolve_leaves(999)

    with pytest.raises(SDWANAddressGroupResolutionError, match="no loaded children"):
        resolver.resolve_leaves(10)


def test_resolve_leaves_keeps_existing_maximum_group_depth() -> None:
    resolver = SDWANAddressGroupLeavesResolver(
        [
            _group(1, group_id=101),
            _group(2, group_id=102, parents=(101,)),
            _group(3, group_id=103, parents=(102,)),
            _group(4, group_id=104, parents=(103,)),
            _host(5, "10.0.0.5", parents=(104,)),
        ]
    )

    with pytest.raises(SDWANAddressGroupResolutionError, match="nesting level"):
        resolver.resolve_leaves(1)
