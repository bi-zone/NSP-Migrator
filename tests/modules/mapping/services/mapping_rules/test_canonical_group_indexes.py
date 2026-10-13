from uuid import UUID, uuid4

import pytest

from app.modules.mapping.domain.exceptions import MappingModuleDomainValidationError
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalAddrObject,
    CanonicalAddrObjKind,
    CanonicalService,
    CanonicalServiceKind,
)
from app.modules.mapping.services.mapping_rules.canonical_addr_objs_index import (
    CanonicalAddrObjectIndex,
)
from app.modules.mapping.services.mapping_rules.canonical_services_index import (
    CanonicalServiceIndex,
)


def _addr_object(
    *,
    object_id: UUID | None = None,
    kind: CanonicalAddrObjKind,
    parent_ids: tuple[UUID, ...] = (),
) -> CanonicalAddrObject:
    return CanonicalAddrObject(
        id=object_id or uuid4(),
        kind=kind,
        name=kind.value,
        parent_ids=parent_ids,
    )


def _service(
    *,
    object_id: UUID | None = None,
    kind: CanonicalServiceKind,
    parent_ids: tuple[UUID, ...] = (),
) -> CanonicalService:
    return CanonicalService(
        id=object_id or uuid4(),
        kind=kind,
        name=kind.value,
        parent_ids=parent_ids,
    )


def test_address_group_index_expands_leaves_and_preserves_hierarchy() -> None:
    root = _addr_object(kind=CanonicalAddrObjKind.ADDR_GROUP)
    nested = _addr_object(
        kind=CanonicalAddrObjKind.ADDR_GROUP,
        parent_ids=(root.id,),
    )
    direct_leaf = _addr_object(
        kind=CanonicalAddrObjKind.HOST,
        parent_ids=(root.id,),
    )
    nested_leaf = _addr_object(
        kind=CanonicalAddrObjKind.SUBNET,
        parent_ids=(nested.id,),
    )
    shared_leaf = _addr_object(
        kind=CanonicalAddrObjKind.FQDN,
        parent_ids=(root.id, nested.id),
    )
    index = CanonicalAddrObjectIndex(
        [root, nested, direct_leaf, nested_leaf, shared_leaf]
    )

    leaves = index.resolve_group_leaves(root.id)
    members = index.resolve_group_members(root.id)

    assert [item.id for item in leaves] == [
        nested_leaf.id,
        shared_leaf.id,
        direct_leaf.id,
    ]
    assert [member.obj.id for member in members] == [
        root.id,
        nested.id,
        nested_leaf.id,
        shared_leaf.id,
        direct_leaf.id,
        shared_leaf.id,
    ]
    assert members[0].parent_id is None
    assert members[1].parent_id == root.id
    assert members[2].depth == 2


def test_address_group_index_rejects_missing_or_non_group_parent() -> None:
    missing_parent_child = _addr_object(
        kind=CanonicalAddrObjKind.HOST,
        parent_ids=(uuid4(),),
    )
    with pytest.raises(MappingModuleDomainValidationError, match="missing parent"):
        CanonicalAddrObjectIndex([missing_parent_child])

    leaf = _addr_object(kind=CanonicalAddrObjKind.HOST)
    child = _addr_object(kind=CanonicalAddrObjKind.HOST, parent_ids=(leaf.id,))
    with pytest.raises(MappingModuleDomainValidationError, match="non-group parent"):
        CanonicalAddrObjectIndex([leaf, child])


def test_service_group_index_detects_cycle_and_maximum_depth() -> None:
    first = _service(kind=CanonicalServiceKind.SERVICE_GROUP)
    second = _service(
        kind=CanonicalServiceKind.SERVICE_GROUP,
        parent_ids=(first.id,),
    )
    cyclic_first = _service(
        object_id=first.id,
        kind=CanonicalServiceKind.SERVICE_GROUP,
        parent_ids=(second.id,),
    )
    cyclic_index = CanonicalServiceIndex([cyclic_first, second])

    with pytest.raises(MappingModuleDomainValidationError, match="Cycle detected"):
        cyclic_index.resolve_group_leaves(first.id)

    root = _service(kind=CanonicalServiceKind.SERVICE_GROUP)
    level_two = _service(
        kind=CanonicalServiceKind.SERVICE_GROUP,
        parent_ids=(root.id,),
    )
    level_three = _service(
        kind=CanonicalServiceKind.SERVICE_GROUP,
        parent_ids=(level_two.id,),
    )
    level_four = _service(
        kind=CanonicalServiceKind.SERVICE_GROUP,
        parent_ids=(level_three.id,),
    )
    deep_index = CanonicalServiceIndex([root, level_two, level_three, level_four])

    with pytest.raises(MappingModuleDomainValidationError, match="depth exceeded"):
        deep_index.resolve_group_members(root.id)


def test_service_group_index_requires_group_root() -> None:
    service = _service(kind=CanonicalServiceKind.TCP)
    index = CanonicalServiceIndex([service])

    with pytest.raises(MappingModuleDomainValidationError, match="not a service group"):
        index.resolve_group_leaves(service.id)
