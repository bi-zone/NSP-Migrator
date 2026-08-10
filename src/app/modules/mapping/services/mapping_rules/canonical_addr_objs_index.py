from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from app.modules.mapping.domain.exceptions import (
    MappingModuleDomainValidationError,
    MappingModuleNotFoundError,
)
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalAddrObject,
    CanonicalAddrObjKind,
)

MAX_GROUP_DEPTH = 3


@dataclass(frozen=True, slots=True)
class CanonicalAddrGroupMember:
    """
    Address group member with hierarchy metadata.

    Used by resolve_group_members() to represent both groups and leaf address
    objects in a flat list while preserving tree structure.

    Attributes:
        obj:
            Canonical address object.
        parent_id:
            Parent group id. None for the root group.
        depth:
            Display depth in the hierarchy. Root group has depth 0.
        path:
            Full path from the root group to this object.
    """

    obj: CanonicalAddrObject
    parent_id: UUID | None
    depth: int
    path: tuple[UUID, ...]

    @property
    def is_group(self) -> bool:
        """Return True if this member is an address group."""

        return self.obj.kind == CanonicalAddrObjKind.ADDR_GROUP


class CanonicalAddrObjectIndex:
    """
    In-memory index for canonical address objects.

    The index provides fast lookup by object id and by parent group id.
    It also validates parent references during construction:

    - object ids must be unique;
    - every parent_id must point to an existing object;
    - every parent_id must point to an address group.

    The index supports two group-resolution modes:

    1. resolve_group_leaves()
       Returns only effective non-group objects.

       Example:

           Group A
             Host 1
             Group B
               Host 2

       Result:

           Host 1
           Host 2

    2. resolve_group_members()
       Returns the whole hierarchy as flat records with parent_id, depth,
       and path metadata.

       Example:

           Group A, depth=0, parent_id=None
           Host 1,  depth=1, parent_id=Group A
           Group B, depth=1, parent_id=Group A
           Host 2,  depth=2, parent_id=Group B
    """

    def __init__(self, addr_objs: list[CanonicalAddrObject]) -> None:
        self._objects_by_id: dict[UUID, CanonicalAddrObject] = {}
        self._children_by_parent_id: dict[UUID, list[CanonicalAddrObject]] = (
            defaultdict(list)
        )

        for obj in addr_objs:
            if obj.id in self._objects_by_id:
                raise MappingModuleDomainValidationError(
                    f"Duplicate canonical address object id: {obj.id}"
                )

            self._objects_by_id[obj.id] = obj

        for obj in addr_objs:
            for parent_id in obj.parent_ids:
                parent = self._objects_by_id.get(parent_id)

                if parent is None:
                    raise MappingModuleDomainValidationError(
                        f"Canonical address object {obj.id} references "
                        f"missing parent {parent_id}"
                    )

                if parent.kind != CanonicalAddrObjKind.ADDR_GROUP:
                    raise MappingModuleDomainValidationError(
                        f"Canonical address object {obj.id} references "
                        f"non-group parent {parent_id}"
                    )

                self._children_by_parent_id[parent_id].append(obj)

    def get(self, addr_obj_id: UUID) -> CanonicalAddrObject:
        """
        Return canonical address object by id.

        Raises:
            MappingModuleNotFoundError:
                If the object does not exist in the index.
        """

        addr_obj = self._objects_by_id.get(addr_obj_id)

        if addr_obj is None:
            raise MappingModuleNotFoundError(
                f"Canonical address object not found: {addr_obj_id}"
            )

        return addr_obj

    def is_group(self, addr_obj_id: UUID) -> bool:
        """
        Return True if object with given id is an address group.

        Raises:
            MappingModuleNotFoundError:
                If the object does not exist in the index.
        """

        return self.get(addr_obj_id).kind == CanonicalAddrObjKind.ADDR_GROUP

    def children_of(self, parent_id: UUID) -> tuple[CanonicalAddrObject, ...]:
        """
        Return direct children of an address object.

        If the object exists but has no children, returns an empty tuple.

        Raises:
            MappingModuleNotFoundError:
                If parent_id does not exist in the index.
        """

        self.get(parent_id)
        return tuple(self._children_by_parent_id.get(parent_id, []))

    def resolve_group_leaves(
        self,
        addr_group_id: UUID,
    ) -> tuple[CanonicalAddrObject, ...]:
        """
        Resolve an address group into its effective leaf address objects.

        This method recursively expands nested address groups and returns only
        non-group address objects. Group objects themselves are not included.

        Example hierarchy:

            Group A
              Host 1
              Group B
                Host 2

        Result for Group A:

            Host 1
            Host 2

        Duplicate leaf objects are returned only once, even if they are
        reachable through multiple nested groups.

        Raises:
            MappingModuleNotFoundError:
                If addr_group_id does not exist.
            MappingModuleDomainValidationError:
                If addr_group_id is not an address group, if group nesting
                exceeds MAX_GROUP_DEPTH, or if a cycle is detected.
        """

        group = self.get(addr_group_id)

        if group.kind != CanonicalAddrObjKind.ADDR_GROUP:
            raise MappingModuleDomainValidationError(
                f"Canonical address object {addr_group_id} is not an address group"
            )

        leaves: list[CanonicalAddrObject] = []
        seen_leaf_ids: set[UUID] = set()

        self._collect_group_leaves(
            group_id=addr_group_id,
            depth=1,
            path=(addr_group_id,),
            leaves=leaves,
            seen_leaf_ids=seen_leaf_ids,
        )

        return tuple(leaves)

    def resolve_group_members(
        self,
        addr_group_id: UUID,
    ) -> tuple[CanonicalAddrGroupMember, ...]:
        """
        Resolve an address group into a flat list of hierarchical members.

        This method returns the group itself, nested groups, and leaf address
        objects. Each returned item includes hierarchy metadata: parent_id,
        display depth, and the full path from the root group to the object.

        Example hierarchy:

            Group A
              Host 1
              Group B
                Host 2

        Result for Group A:

            Group A, depth=0, parent_id=None
            Host 1,  depth=1, parent_id=Group A
            Group B, depth=1, parent_id=Group A
            Host 2,  depth=2, parent_id=Group B

        Unlike resolve_group_leaves(), this method does not deduplicate objects.
        If the same object is reachable through multiple branches, it may appear
        multiple times with different parent_id and path values.

        Raises:
            MappingModuleNotFoundError:
                If addr_group_id does not exist.
            MappingModuleDomainValidationError:
                If addr_group_id is not an address group, if group nesting
                exceeds MAX_GROUP_DEPTH, or if a cycle is detected.
        """

        group = self.get(addr_group_id)

        if group.kind != CanonicalAddrObjKind.ADDR_GROUP:
            raise MappingModuleDomainValidationError(
                f"Canonical address object {addr_group_id} is not an address group"
            )

        result: list[CanonicalAddrGroupMember] = []

        self._collect_group_members(
            group_id=addr_group_id,
            parent_id=None,
            group_depth=1,
            display_depth=0,
            path=(addr_group_id,),
            result=result,
        )

        return tuple(result)

    def _collect_group_leaves(
        self,
        *,
        group_id: UUID,
        depth: int,
        path: tuple[UUID, ...],
        leaves: list[CanonicalAddrObject],
        seen_leaf_ids: set[UUID],
    ) -> None:
        """
        Recursively collect effective leaf address objects for a group.

        A leaf is any non-group canonical address object. Nested address groups
        are traversed, but are not added to the result.

        Example hierarchy:

            Group A
              Host 1
              Group B
                Host 2

        Collected leaves:

            Host 1
            Host 2

        This helper mutates `leaves` and `seen_leaf_ids` in place.

        Args:
            group_id:
                Current group being expanded.
            depth:
                Current group nesting depth. The root group starts at depth 1.
            path:
                Group path used to detect cycles and build readable error
                messages.
            leaves:
                Output list of collected non-group address objects.
            seen_leaf_ids:
                Set used to avoid returning the same leaf object more than once.

        Raises:
            MappingModuleDomainValidationError:
                If nesting exceeds MAX_GROUP_DEPTH or a cycle is detected.
        """

        if depth > MAX_GROUP_DEPTH:
            path_str = " -> ".join(str(item) for item in path)

            raise MappingModuleDomainValidationError(
                f"Canonical address group nesting depth exceeded. "
                f"Max depth is {MAX_GROUP_DEPTH}. Path: {path_str}"
            )

        for child in self._children_by_parent_id.get(group_id, []):
            if child.kind == CanonicalAddrObjKind.ADDR_GROUP:
                if child.id in path:
                    cycle = " -> ".join(str(item) for item in (*path, child.id))
                    raise MappingModuleDomainValidationError(
                        f"Cycle detected in canonical address groups: {cycle}"
                    )

                self._collect_group_leaves(
                    group_id=child.id,
                    depth=depth + 1,
                    path=(*path, child.id),
                    leaves=leaves,
                    seen_leaf_ids=seen_leaf_ids,
                )
                continue

            if child.id in seen_leaf_ids:
                continue

            seen_leaf_ids.add(child.id)
            leaves.append(child)

    def _collect_group_members(
        self,
        *,
        group_id: UUID,
        parent_id: UUID | None,
        group_depth: int,
        display_depth: int,
        path: tuple[UUID, ...],
        result: list[CanonicalAddrGroupMember],
    ) -> None:
        """
        Recursively collect the full group hierarchy as flat member records.

        This helper includes both group objects and non-group address objects.
        It preserves hierarchy information by storing each member's parent_id,
        display depth, and full path from the root group.

        Example hierarchy:

            Group A
              Host 1
              Group B
                Host 2

        Collected members:

            Group A, depth=0, parent_id=None
            Host 1,  depth=1, parent_id=Group A
            Group B, depth=1, parent_id=Group A
            Host 2,  depth=2, parent_id=Group B

        This helper mutates `result` in place.

        Args:
            group_id:
                Current group being added and expanded.
            parent_id:
                Parent group id for the current group. None for the root group.
            group_depth:
                Current group nesting depth used for MAX_GROUP_DEPTH validation.
                The root group starts at group_depth=1.
            display_depth:
                Visual hierarchy depth returned in CanonicalAddrGroupMember.
                The root group starts at display_depth=0.
            path:
                Full path from the root group to the current object. Used for
                cycle detection and readable error messages.
            result:
                Output list of CanonicalAddrGroupMember records.

        Raises:
            MappingModuleDomainValidationError:
                If nesting exceeds MAX_GROUP_DEPTH or a cycle is detected.
        """

        if group_depth > MAX_GROUP_DEPTH:
            path_str = " -> ".join(str(item) for item in path)

            raise MappingModuleDomainValidationError(
                f"Canonical address group nesting depth exceeded. "
                f"Max depth is {MAX_GROUP_DEPTH}. Path: {path_str}"
            )

        group = self.get(group_id)

        result.append(
            CanonicalAddrGroupMember(
                obj=group,
                parent_id=parent_id,
                depth=display_depth,
                path=path,
            )
        )

        for child in self._children_by_parent_id.get(group_id, []):
            if child.kind == CanonicalAddrObjKind.ADDR_GROUP:
                if child.id in path:
                    cycle = " -> ".join(str(item) for item in (*path, child.id))

                    raise MappingModuleDomainValidationError(
                        f"Cycle detected in canonical address groups: {cycle}"
                    )

                self._collect_group_members(
                    group_id=child.id,
                    parent_id=group_id,
                    group_depth=group_depth + 1,
                    display_depth=display_depth + 1,
                    path=(*path, child.id),
                    result=result,
                )
                continue

            result.append(
                CanonicalAddrGroupMember(
                    obj=child,
                    parent_id=group_id,
                    depth=display_depth + 1,
                    path=(*path, child.id),
                )
            )
