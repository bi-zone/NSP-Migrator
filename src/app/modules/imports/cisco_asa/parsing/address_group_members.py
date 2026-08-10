from __future__ import annotations

from app.modules.imports.cisco_asa.domain.parsed_config import (
    ParsedConfig,
    ParsedObjectType,
)


def normalize_address_group_members(parsed: ParsedConfig) -> None:  # noqa: C901
    """Convert address-group member dicts into string refs for the normalizer.

    Walks parsed.address_objects where kind == ADDRESS_GROUP and
    replaces payload["members"] with a list of strings consumed by
    _materialize_address_group_members in normalizer/addresses.py.

    Mapping rules (from parsing/extractors/addresses.py shapes):
    - {type: host, ip} -> host:{ip}
    - {type: subnet, ip, mask} -> net:{ip}/{mask}
    - {type: object|group, name} -> {name} (bare object key)
    - existing str members are kept unchanged

    Unrecognized dict shapes are dropped silently. Asserted behavior in
    test_parse_network_object_object_member_refs (no malformed net:object/
    refs).

    Side Effects:
        Mutates obj.payload["members"] lists in place on parsed.
    """
    for obj in parsed.address_objects:
        if obj.kind != ParsedObjectType.ADDRESS_GROUP:
            continue

        members = obj.payload.get("members")
        if not members:
            continue

        normalized: list[str] = []
        for member in members:
            if isinstance(member, str):
                normalized.append(member)
                continue
            if not isinstance(member, dict):
                continue
            member_type = (member.get("type") or "").lower()
            if member_type == "host" and member.get("ip"):
                normalized.append(f"host:{member['ip']}")
            elif member_type == "subnet" and member.get("ip") and member.get("mask"):
                normalized.append(f"net:{member['ip']}/{member['mask']}")
            elif member_type == "object" and member.get("name"):
                normalized.append(str(member["name"]))
            elif member_type == "group" and member.get("name"):
                normalized.append(str(member["name"]))

        obj.payload["members"] = normalized