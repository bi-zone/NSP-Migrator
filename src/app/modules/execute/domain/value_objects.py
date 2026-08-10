from dataclasses import dataclass
from typing import Any, Self

from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
    SdwanService,
    SdwanZone,
)
from app.modules.execute.domain.enums import RuleMatchStatus, SdwanRuleAction


@dataclass(frozen=True, slots=True)
class RuleBody:
    """Comparable firewall rule body.

    The object stores only semantic references used by execute comparison logic:
    action, zones, address objects and services. It intentionally has no database
    identity and no SD-WAN lifecycle metadata, so both planned rules and existing
    SD-WAN rules can be normalized through the same code path.
    """

    action: SdwanRuleAction
    src_zones: list[int]
    dst_zones: list[int]
    src_addr_objects: list[int]
    dst_addr_objects: list[int]
    services: list[int]


@dataclass(frozen=True, slots=True)
class PlannedRuleDraft(RuleBody):
    """Rule body prepared from Mapping data and planned for SD-WAN creation."""

    @classmethod
    def from_dict(cls, data: dict[str, str | list[int]]) -> Self:
        """Restore draft from JSON-compatible DB payload."""

        def _to_int_list(raw_data: Any) -> list[int]:
            if not isinstance(raw_data, list):
                raise ValueError(f"Expected list, not {type(raw_data)}")
            return [int(item) for item in raw_data]

        return cls(
            action=SdwanRuleAction(data["action"]),  # type: ignore
            src_zones=_to_int_list(data["src_zones"]),
            dst_zones=_to_int_list(data["dst_zones"]),
            src_addr_objects=_to_int_list(data["src_addr_objects"]),
            dst_addr_objects=_to_int_list(data["dst_addr_objects"]),
            services=_to_int_list(data["services"]),
        )

    def to_dict(self) -> dict[str, int | str | list[int]]:
        """Return JSON-compatible representation for DB/API serialization."""
        return {
            "action": self.action.value,
            "src_zones": self.src_zones,
            "dst_zones": self.dst_zones,
            "src_addr_objects": self.src_addr_objects,
            "dst_addr_objects": self.dst_addr_objects,
            "services": self.services,
        }


@dataclass(frozen=True, slots=True)
class SdwanRule(RuleBody):
    """Existing SD-WAN rule loaded only into runtime execute catalog."""

    id: int


@dataclass(frozen=True, slots=True)
class SdwanPolicyCatalog:
    """Runtime SD-WAN policy catalog used by execute module.

    The catalog is loaded from SD-WAN during plan preparation and contains only
    data required to compare planned rules with already existing SD-WAN rules:
    firewall rules, zones, services and address objects.

    This object is intentionally in-memory only. Execute module does not persist
    it because the catalog is not a business artifact and is not reused after the
    comparison. If historical or audit data is needed later, it should be written
    to a separate reporting model, not to the execute plan aggregate.
    """

    target_id: str
    rules: list[SdwanRule]
    zones: list[SdwanZone]
    services: list[SdwanService]
    address_objects: list[SdwanAddrObject]


@dataclass(frozen=True, slots=True)
class RuleCompareResult:
    """Flat comparison result stored directly on ExecutePlanRule."""

    match_status: RuleMatchStatus
    matched_sdwan_rule_id: int | None
    match_info: str
