from collections import defaultdict

from app.integrations.sdwan_csp_api.gateways.enums import SdwanAddrObjectType
from app.integrations.sdwan_csp_api.gateways.models import SdwanAddrObject

MAX_ADDR_GROUP_NESTING_LEVEL = 3


class SDWANAddressGroupResolutionError(ValueError):
    """An address object cannot be resolved to leaf SD-WAN objects."""


class SDWANAddressGroupLeavesResolver:
    """Resolve one address object or group into its loaded leaf objects.

    ``SDWANCatalogGateway`` supplies the expanded flat catalog. This resolver
    performs only in-memory traversal through the ``parents`` links, so it can
    be shared by consumers that need different error policies.
    """

    def __init__(self, address_objects: list[SdwanAddrObject]) -> None:
        self._objects_by_id = {
            int(address_object.id): address_object for address_object in address_objects
        }
        self._children_by_parent: dict[int, list[SdwanAddrObject]] = defaultdict(list)
        for address_object in address_objects:
            for parent_id in address_object.parents:
                self._children_by_parent[int(parent_id)].append(address_object)

    def resolve_leaves(self, address_object_id: int) -> tuple[SdwanAddrObject, ...]:
        """Return leaf objects for one address object or address group."""
        return tuple(
            self._resolve_leaves(
                address_object_id=address_object_id,
                current_group_level=0,
            )
        )

    def _resolve_leaves(
        self,
        *,
        address_object_id: int,
        current_group_level: int,
    ) -> list[SdwanAddrObject]:
        address_object = self._objects_by_id.get(address_object_id)
        if address_object is None:
            raise SDWANAddressGroupResolutionError(
                f"Unknown address object id: {address_object_id}"
            )

        if address_object.type != SdwanAddrObjectType.ADDR_GROUP:
            return [address_object]

        group_level = current_group_level + 1
        if group_level > MAX_ADDR_GROUP_NESTING_LEVEL:
            raise SDWANAddressGroupResolutionError(
                "Address group nesting level exceeded: "
                f"group object id={address_object.id}, "
                f"group value={address_object.addr_group}, "
                f"level={group_level}, "
                f"max_level={MAX_ADDR_GROUP_NESTING_LEVEL}"
            )

        group_id = address_object.addr_group or address_object.id
        children = self._children_by_parent.get(int(group_id), [])
        if not children:
            raise SDWANAddressGroupResolutionError(
                f"Address group {group_id} has no loaded children"
            )

        leaves: list[SdwanAddrObject] = []
        for child in children:
            if child.id == address_object.id:
                continue
            leaves.extend(
                self._resolve_leaves(
                    address_object_id=child.id,
                    current_group_level=group_level,
                )
            )

        if not leaves:
            raise SDWANAddressGroupResolutionError(
                f"Address group {address_object.id} has no leaf children"
            )

        return leaves
