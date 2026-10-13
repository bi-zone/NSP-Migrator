from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.modules.canonical.domain import ObjectFamily
from app.modules.canonical.domain.enums import ObjectKind
from app.modules.canonical.domain.object import CanonicalObject, CanonicalObjectMember
from app.modules.canonical.services.group_expansion import expand_object_groups


class _FakeObjectRepository:
    def __init__(self) -> None:
        self.objects_by_id: dict[UUID, CanonicalObject] = {}
        self.members_by_parent: dict[UUID, list[CanonicalObjectMember]] = {}

    async def get_by_ids_for_snapshot(
        self, *, canonical_snapshot_id: UUID, object_ids: list[UUID]
    ) -> list[CanonicalObject]:
        _ = canonical_snapshot_id
        return [
            self.objects_by_id[object_id]
            for object_id in object_ids
            if object_id in self.objects_by_id
        ]

    async def get_members_by_parents(
        self, *, canonical_snapshot_id: UUID, parent_object_ids: list[UUID]
    ) -> list[CanonicalObjectMember]:
        _ = canonical_snapshot_id
        members: list[CanonicalObjectMember] = []
        for parent_id in parent_object_ids:
            members.extend(self.members_by_parent.get(parent_id, []))
        return members


@pytest.mark.asyncio
async def test_expand_object_groups_walks_nested_groups() -> None:
    snapshot_id = uuid4()
    leaf = CanonicalObject.create(
        canonical_snapshot_id=snapshot_id,
        object_key="leaf",
        object_family=ObjectFamily.ADDR,
        object_kind=ObjectKind.HOST,
        name="leaf",
    )
    group = CanonicalObject.create(
        canonical_snapshot_id=snapshot_id,
        object_key="group",
        object_family=ObjectFamily.ADDR,
        object_kind=ObjectKind.ADDR_GROUP,
        name="group",
    )
    repo = _FakeObjectRepository()
    repo.objects_by_id = {leaf.id: leaf, group.id: group}
    repo.members_by_parent = {
        group.id: [
            CanonicalObjectMember.create(
                parent_object_id=group.id,
                child_object_id=leaf.id,
                position=0,
            )
        ]
    }

    objects, parent_ids = await expand_object_groups(
        objects=repo,
        canonical_snapshot_id=snapshot_id,
        seed_ids={group.id},
    )

    collected_ids = {obj.id for obj in objects}
    assert leaf.id in collected_ids
    assert group.id in collected_ids
    assert parent_ids[leaf.id] == {group.id}


@pytest.mark.asyncio
async def test_expand_object_groups_stops_on_cycles_and_keeps_both_edges() -> None:
    """Guard malformed cyclic memberships without losing lineage metadata."""
    snapshot_id = uuid4()
    group_a = CanonicalObject.create(
        canonical_snapshot_id=snapshot_id,
        object_key="group-a",
        object_family=ObjectFamily.ADDR,
        object_kind=ObjectKind.ADDR_GROUP,
        name="group-a",
    )
    group_b = CanonicalObject.create(
        canonical_snapshot_id=snapshot_id,
        object_key="group-b",
        object_family=ObjectFamily.ADDR,
        object_kind=ObjectKind.ADDR_GROUP,
        name="group-b",
    )
    repo = _FakeObjectRepository()
    repo.objects_by_id = {group_a.id: group_a, group_b.id: group_b}
    repo.members_by_parent = {
        group_a.id: [
            CanonicalObjectMember.create(
                parent_object_id=group_a.id,
                child_object_id=group_b.id,
            )
        ],
        group_b.id: [
            CanonicalObjectMember.create(
                parent_object_id=group_b.id,
                child_object_id=group_a.id,
            )
        ],
    }

    objects, parent_ids = await expand_object_groups(
        objects=repo,
        canonical_snapshot_id=snapshot_id,
        seed_ids={group_a.id},
    )

    assert {obj.id for obj in objects} == {group_a.id, group_b.id}
    assert parent_ids[group_b.id] == {group_a.id}
    assert parent_ids[group_a.id] == {group_b.id}


@pytest.mark.asyncio
async def test_expand_object_groups_handles_shared_and_missing_children() -> None:
    """Record multiple parents and safely ignore dangling child IDs."""
    snapshot_id = uuid4()
    leaf = CanonicalObject.create(
        canonical_snapshot_id=snapshot_id,
        object_key="shared-leaf",
        object_family=ObjectFamily.ADDR,
        object_kind=ObjectKind.HOST,
        name="shared-leaf",
    )
    groups = [
        CanonicalObject.create(
            canonical_snapshot_id=snapshot_id,
            object_key=f"group-{index}",
            object_family=ObjectFamily.ADDR,
            object_kind=ObjectKind.ADDR_GROUP,
            name=f"group-{index}",
        )
        for index in range(2)
    ]
    dangling_id = uuid4()
    repo = _FakeObjectRepository()
    repo.objects_by_id = {leaf.id: leaf, **{group.id: group for group in groups}}
    repo.members_by_parent = {
        group.id: [
            CanonicalObjectMember.create(
                parent_object_id=group.id,
                child_object_id=leaf.id,
                position=0,
            ),
            CanonicalObjectMember.create(
                parent_object_id=group.id,
                child_object_id=dangling_id,
                position=1,
            ),
        ]
        for group in groups
    }

    objects, parent_ids = await expand_object_groups(
        objects=repo,
        canonical_snapshot_id=snapshot_id,
        seed_ids={group.id for group in groups},
    )

    assert {obj.id for obj in objects} == {leaf.id, *(group.id for group in groups)}
    assert parent_ids[leaf.id] == {group.id for group in groups}
    assert parent_ids[dangling_id] == {group.id for group in groups}
