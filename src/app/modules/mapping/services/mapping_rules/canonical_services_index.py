from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from app.modules.mapping.domain.exceptions import (
    MappingModuleDomainValidationError,
    MappingModuleNotFoundError,
)
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalService,
    CanonicalServiceKind,
)

MAX_GROUP_DEPTH = 3


@dataclass(frozen=True, slots=True)
class CanonicalServiceGroupMember:
    """
    Service group member with hierarchy metadata.

    Used by resolve_group_members() to represent both service groups and leaf
    service objects in a flat list while preserving tree structure.

    Attributes:
        obj:
            Canonical service object.
        parent_id:
            Parent service group id. None for the root group.
        depth:
            Display depth in the hierarchy. Root group has depth 0.
        path:
            Full path from the root group to this object.
    """

    obj: CanonicalService
    parent_id: UUID | None
    depth: int
    path: tuple[UUID, ...]

    @property
    def is_group(self) -> bool:
        """Return True if this member is a service group."""

        return self.obj.kind == CanonicalServiceKind.SERVICE_GROUP


class CanonicalServiceIndex:
    """
    In-memory index for canonical service objects.

    The index provides fast lookup by service id and by parent service group id.
    It also validates parent references during construction:

    - service ids must be unique;
    - every parent_id must point to an existing service object;
    - every parent_id must point to a service group.

    The index supports two group-resolution modes:

    1. resolve_group_leaves()
       Returns only effective non-group services.

       Example:

           Group A
             HTTP
             Group B
               HTTPS

       Result:

           HTTP
           HTTPS

    2. resolve_group_members()
       Returns the whole hierarchy as flat records with parent_id, depth,
       and path metadata.

       Example:

           Group A, depth=0, parent_id=None
           HTTP,    depth=1, parent_id=Group A
           Group B, depth=1, parent_id=Group A
           HTTPS,   depth=2, parent_id=Group B
    """

    def __init__(self, services_objs: list[CanonicalService]) -> None:
        self._objects_by_id: dict[UUID, CanonicalService] = {}
        self._children_by_parent_id: dict[UUID, list[CanonicalService]] = defaultdict(
            list
        )

        for obj in services_objs:
            if obj.id in self._objects_by_id:
                raise MappingModuleDomainValidationError(
                    f"Duplicate canonical service object id: {obj.id}"
                )

            self._objects_by_id[obj.id] = obj

        for obj in services_objs:
            for parent_id in obj.parent_ids:
                parent = self._objects_by_id.get(parent_id)

                if parent is None:
                    raise MappingModuleDomainValidationError(
                        f"Canonical service object {obj.id} references "
                        f"missing parent {parent_id}"
                    )

                if parent.kind != CanonicalServiceKind.SERVICE_GROUP:
                    raise MappingModuleDomainValidationError(
                        f"Canonical service object {obj.id} references "
                        f"non-group parent {parent_id}"
                    )

                self._children_by_parent_id[parent_id].append(obj)

    def get(self, serv_obj_id: UUID) -> CanonicalService:
        """
        Return canonical service object by id.

        Raises:
            MappingModuleNotFoundError:
                If the service object does not exist in the index.
        """

        serv_obj = self._objects_by_id.get(serv_obj_id)

        if serv_obj is None:
            raise MappingModuleNotFoundError(
                f"Canonical service object not found: {serv_obj_id}"
            )

        return serv_obj

    def is_group(self, serv_obj_id: UUID) -> bool:
        """
        Return True if service object with given id is a service group.

        Raises:
            MappingModuleNotFoundError:
                If the service object does not exist in the index.
        """

        return self.get(serv_obj_id).kind == CanonicalServiceKind.SERVICE_GROUP

    def children_of(self, parent_id: UUID) -> tuple[CanonicalService, ...]:
        """
        Return direct children of a service object.

        If the object exists but has no children, returns an empty tuple.

        Raises:
            MappingModuleNotFoundError:
                If parent_id does not exist in the index.
        """

        self.get(parent_id)
        return tuple(self._children_by_parent_id.get(parent_id, []))

    def resolve_group_leaves(self, serv_group_id: UUID) -> tuple[CanonicalService, ...]:
        """
        Resolve a service group into its effective leaf service objects.

        This method recursively expands nested service groups and returns only
        non-group service objects. Service group objects themselves are not
        included.

        Example hierarchy:

            Group A
              HTTP
              Group B
                HTTPS

        Result for Group A:

            HTTP
            HTTPS

        Duplicate leaf services are returned only once, even if they are
        reachable through multiple nested groups.

        Raises:
            MappingModuleNotFoundError:
                If serv_group_id does not exist.
            MappingModuleDomainValidationError:
                If serv_group_id is not a service group, if group nesting
                exceeds MAX_GROUP_DEPTH, or if a cycle is detected.
        """

        group = self.get(serv_group_id)

        if group.kind != CanonicalServiceKind.SERVICE_GROUP:
            raise MappingModuleDomainValidationError(
                f"Canonical service object {serv_group_id} is not a service group"
            )

        leaves: list[CanonicalService] = []
        seen_leaf_ids: set[UUID] = set()

        self._collect_group_leaves(
            group_id=serv_group_id,
            depth=1,
            path=(serv_group_id,),
            leaves=leaves,
            seen_leaf_ids=seen_leaf_ids,
        )

        return tuple(leaves)

    def resolve_group_members(
        self,
        serv_group_id: UUID,
    ) -> tuple[CanonicalServiceGroupMember, ...]:
        """
        Resolve a service group into a flat list of hierarchical members.

        This method returns the group itself, nested groups, and leaf service
        objects. Each returned item includes hierarchy metadata: parent_id,
        display depth, and the full path from the root group to the object.

        Example hierarchy:

            Group A
              HTTP
              Group B
                HTTPS

        Result for Group A:

            Group A, depth=0, parent_id=None
            HTTP,    depth=1, parent_id=Group A
            Group B, depth=1, parent_id=Group A
            HTTPS,   depth=2, parent_id=Group B

        Unlike resolve_group_leaves(), this method does not deduplicate objects.
        If the same service is reachable through multiple branches, it may
        appear multiple times with different parent_id and path values.

        Raises:
            MappingModuleNotFoundError:
                If serv_group_id does not exist.
            MappingModuleDomainValidationError:
                If serv_group_id is not a service group, if group nesting
                exceeds MAX_GROUP_DEPTH, or if a cycle is detected.
        """

        group = self.get(serv_group_id)

        if group.kind != CanonicalServiceKind.SERVICE_GROUP:
            raise MappingModuleDomainValidationError(
                f"Canonical service object {serv_group_id} is not a service group"
            )

        result: list[CanonicalServiceGroupMember] = []

        self._collect_group_members(
            group_id=serv_group_id,
            parent_id=None,
            group_depth=1,
            display_depth=0,
            path=(serv_group_id,),
            result=result,
        )

        return tuple(result)

    def _collect_group_leaves(
        self,
        *,
        group_id: UUID,
        depth: int,
        path: tuple[UUID, ...],
        leaves: list[CanonicalService],
        seen_leaf_ids: set[UUID],
    ) -> None:
        """
        Recursively collect effective leaf service objects for a group.

        A leaf is any non-group canonical service object. Nested service groups
        are traversed, but are not added to the result.

        Example hierarchy:

            Group A
              HTTP
              Group B
                HTTPS

        Collected leaves:

            HTTP
            HTTPS

        This helper mutates `leaves` and `seen_leaf_ids` in place.

        Args:
            group_id:
                Current service group being expanded.
            depth:
                Current group nesting depth. The root group starts at depth 1.
            path:
                Group path used to detect cycles and build readable error
                messages.
            leaves:
                Output list of collected non-group service objects.
            seen_leaf_ids:
                Set used to avoid returning the same leaf object more than once.

        Raises:
            MappingModuleDomainValidationError:
                If nesting exceeds MAX_GROUP_DEPTH or a cycle is detected.
        """

        if depth > MAX_GROUP_DEPTH:
            path_str = " -> ".join(str(item) for item in path)

            raise MappingModuleDomainValidationError(
                f"Canonical service group nesting depth exceeded. "
                f"Max depth is {MAX_GROUP_DEPTH}. Path: {path_str}"
            )

        for child in self._children_by_parent_id.get(group_id, []):
            if child.kind == CanonicalServiceKind.SERVICE_GROUP:
                if child.id in path:
                    cycle = " -> ".join(str(item) for item in (*path, child.id))
                    raise MappingModuleDomainValidationError(
                        f"Cycle detected in canonical service groups: {cycle}"
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
        result: list[CanonicalServiceGroupMember],
    ) -> None:
        """
        Recursively collect the full service group hierarchy as flat records.

        This helper includes both service group objects and non-group service
        objects. It preserves hierarchy information by storing each member's
        parent_id, display depth, and full path from the root group.

        Example hierarchy:

            Group A
              HTTP
              Group B
                HTTPS

        Collected members:

            Group A, depth=0, parent_id=None
            HTTP,    depth=1, parent_id=Group A
            Group B, depth=1, parent_id=Group A
            HTTPS,   depth=2, parent_id=Group B

        This helper mutates `result` in place.

        Args:
            group_id:
                Current service group being added and expanded.
            parent_id:
                Parent service group id for the current group. None for the
                root group.
            group_depth:
                Current group nesting depth used for MAX_GROUP_DEPTH validation.
                The root group starts at group_depth=1.
            display_depth:
                Visual hierarchy depth returned in CanonicalServiceGroupMember.
                The root group starts at display_depth=0.
            path:
                Full path from the root group to the current object. Used for
                cycle detection and readable error messages.
            result:
                Output list of CanonicalServiceGroupMember records.

        Raises:
            MappingModuleDomainValidationError:
                If nesting exceeds MAX_GROUP_DEPTH or a cycle is detected.
        """

        if group_depth > MAX_GROUP_DEPTH:
            path_str = " -> ".join(str(item) for item in path)

            raise MappingModuleDomainValidationError(
                f"Canonical service group nesting depth exceeded. "
                f"Max depth is {MAX_GROUP_DEPTH}. Path: {path_str}"
            )

        group = self.get(group_id)

        result.append(
            CanonicalServiceGroupMember(
                obj=group,
                parent_id=parent_id,
                depth=display_depth,
                path=path,
            )
        )

        for child in self._children_by_parent_id.get(group_id, []):
            if child.kind == CanonicalServiceKind.SERVICE_GROUP:
                if child.id in path:
                    cycle = " -> ".join(str(item) for item in (*path, child.id))

                    raise MappingModuleDomainValidationError(
                        f"Cycle detected in canonical service groups: {cycle}"
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
                CanonicalServiceGroupMember(
                    obj=child,
                    parent_id=group_id,
                    depth=display_depth + 1,
                    path=(*path, child.id),
                )
            )
