"""Transitive expansion of address/service group operands for rule scope."""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from app.modules.canonical.domain.enums import ObjectKind
from app.modules.canonical.domain.object import CanonicalObject
from app.modules.canonical.ports.object_repository import CanonicalObjectRepositoryPort

_GROUP_KINDS: frozenset[ObjectKind] = frozenset(
    {ObjectKind.ADDR_GROUP, ObjectKind.SERVICE_GROUP}
)


async def expand_object_groups(
    *,
    objects: CanonicalObjectRepositoryPort,
    canonical_snapshot_id: UUID,
    seed_ids: set[UUID],
) -> tuple[list[CanonicalObject], dict[UUID, set[UUID]]]:
    """Walk group membership edges and collect all referenced objects.

    Returns collected objects and a map of child object id to parent group ids.
    """
    collected: dict[UUID, CanonicalObject] = {}
    parent_ids: dict[UUID, set[UUID]] = defaultdict(set)
    pending: set[UUID] = set(seed_ids)
    seen: set[UUID] = set(seed_ids)  # cycle guard: skip already-visited children

    while pending:
        batch_ids = list(pending)
        pending.clear()

        batch = await objects.get_by_ids_for_snapshot(
            canonical_snapshot_id=canonical_snapshot_id,
            object_ids=batch_ids,
        )
        for obj in batch:
            collected.setdefault(obj.id, obj)

        group_ids = [obj.id for obj in batch if obj.object_kind in _GROUP_KINDS]
        if not group_ids:
            continue

        members = await objects.get_members_by_parents(
            canonical_snapshot_id=canonical_snapshot_id,
            parent_object_ids=group_ids,
        )
        for member in members:
            parent_ids[member.child_object_id].add(member.parent_object_id)
            if member.child_object_id in seen:
                continue
            seen.add(member.child_object_id)
            pending.add(member.child_object_id)

    return list(collected.values()), dict(parent_ids)
