from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.modules.mapping.application.dto import (
    CanonicalEntityDisplayDTO,
    CanonicalRuleDisplayDTO,
    CanonicalToSdwanEntityProjectionDTO,
    MappedSdwanEntityDisplayDTO,
    MappingCanonicalRuleProjectionDTO,
    MappingScopeRuleDisplayDTO,
    MappingScopeRulesProjectionDTO,
)
from app.modules.mapping.domain.enums import (
    MappedRuleStatus,
    MappingResultStatus,
    MappingScopeRuleOperandRole,
)

SELECTED_MAPPED_RULE_ID_KEY = "mapped_rules_selected_rule_id"

ROLE_FIELD_BY_ROLE: dict[MappingScopeRuleOperandRole, str] = {
    MappingScopeRuleOperandRole.SRC_ZONE: "src_zones",
    MappingScopeRuleOperandRole.DST_ZONE: "dst_zones",
    MappingScopeRuleOperandRole.SRC_ADDR_OBJECT: "src_addr_objects",
    MappingScopeRuleOperandRole.DST_ADDR_OBJECT: "dst_addr_objects",
    MappingScopeRuleOperandRole.SERVICE: "services",
}

ROLE_COLUMN_BY_ROLE: dict[MappingScopeRuleOperandRole, str] = {
    MappingScopeRuleOperandRole.SRC_ZONE: "src_zone",
    MappingScopeRuleOperandRole.DST_ZONE: "dst_zone",
    MappingScopeRuleOperandRole.SRC_ADDR_OBJECT: "src_object",
    MappingScopeRuleOperandRole.DST_ADDR_OBJECT: "dst_object",
    MappingScopeRuleOperandRole.SERVICE: "service",
}

ROLE_BY_COLUMN: dict[str, MappingScopeRuleOperandRole] = {
    column: role for role, column in ROLE_COLUMN_BY_ROLE.items()
}

ENTITY_ROLE_LABELS: dict[MappingScopeRuleOperandRole, str] = {
    MappingScopeRuleOperandRole.SRC_ZONE: "SRC zone",
    MappingScopeRuleOperandRole.DST_ZONE: "DST zone",
    MappingScopeRuleOperandRole.SRC_ADDR_OBJECT: "SRC objects",
    MappingScopeRuleOperandRole.DST_ADDR_OBJECT: "DST objects",
    MappingScopeRuleOperandRole.SERVICE: "Services",
}


@dataclass(slots=True)
class MappedRulesProjectionState:
    projection: MappingScopeRulesProjectionDTO
    canonical_rule_by_id: dict[str, CanonicalRuleDisplayDTO]
    mapped_rule_by_id: dict[str, MappingScopeRuleDisplayDTO]
    details_by_rule_id: dict[str, MappingCanonicalRuleProjectionDTO]

    @property
    def mapping_scope_id(self) -> UUID:
        return self.projection.mapping_scope_id

    @property
    def canonical_rules(self) -> list[CanonicalRuleDisplayDTO]:
        return self.projection.canonical_rules

    @property
    def mapped_rules(self) -> list[MappingScopeRuleDisplayDTO]:
        return self.projection.mapped_rules

    @property
    def unmatched_rules_count(self) -> int:
        return sum(
            1
            for rule in self.projection.mapped_rules
            if rule.status != MappedRuleStatus.MAPPED
        )


class StatusStyleColor(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"
    GRAY = "GRAY"


STATUS_CELL_STYLE: dict[StatusStyleColor, str] = {
    StatusStyleColor.GREEN: "background-color: #dcfce7; color: #166534; font-weight: 600;",
    StatusStyleColor.YELLOW: "background-color: #fef3c7; color: #92400e; font-weight: 700;",
    StatusStyleColor.RED: "background-color: #fee2e2; color: #991b1b; font-weight: 700;",
    StatusStyleColor.GRAY: "background-color: #f3f4f6; color: #374151;",
}

MATCHED_STATUSES = {MappingResultStatus.MATCHED}


def dash(value: object | None) -> str:
    return "—" if value is None or value == "" else str(value)


def short_uuid(value: object | None) -> str:
    if value is None:
        return "—"
    value_str = str(value)
    return value_str[:8]


def entity_names_to_text(rows: list[CanonicalEntityDisplayDTO]) -> str:
    values = [entity.name for entity in rows if entity and entity.name]
    return "; ".join(values) if values else "—"


def sdwan_names_to_text(rows: list[MappedSdwanEntityDisplayDTO]) -> str:
    values: list[str] = []
    for entity in rows:
        if entity.match_status == MappingResultStatus.AMBIGUOUS:
            values.append("<AMBIGUOUS>")
        elif entity.match_status == MappingResultStatus.UNRESOLVED:
            values.append("<UNRESOLVED>")
        elif entity.name:
            values.append(entity.name)
        else:
            values.append("—")

    return "; ".join(values) if values else "—"


def rule_rows_for_role(
    details: MappingCanonicalRuleProjectionDTO,
    role: MappingScopeRuleOperandRole,
) -> list[CanonicalToSdwanEntityProjectionDTO]:
    return list(getattr(details, ROLE_FIELD_BY_ROLE[role]))


def canonical_entities_for_role(
    canonical_rule: CanonicalRuleDisplayDTO,
    role: MappingScopeRuleOperandRole,
) -> list[CanonicalEntityDisplayDTO]:
    return list(getattr(canonical_rule, ROLE_FIELD_BY_ROLE[role]))


def mapped_entities_for_role(
    mapped_rule: MappingScopeRuleDisplayDTO,
    role: MappingScopeRuleOperandRole,
) -> list[MappedSdwanEntityDisplayDTO]:
    return list(getattr(mapped_rule, ROLE_FIELD_BY_ROLE[role]))


def count_need_mapping(rows: list[CanonicalToSdwanEntityProjectionDTO]) -> int:
    """
    Counts only real SD-WAN mapping rows.

    Canonical group placeholder has sdwan=None and is intentionally ignored:
    it is a display-only canonical row, not a missing SD-WAN mapping.
    """
    return sum(
        1
        for row in rows
        if row.sdwan is not None
        and row.sdwan.match_status != MappingResultStatus.MATCHED
    )


def has_selected_sdwan_entity(
    rows: list[CanonicalToSdwanEntityProjectionDTO],
) -> bool:
    return any(
        row.sdwan is not None
        and row.sdwan.match_status == MappingResultStatus.MATCHED
        and row.sdwan.sdwan_id is not None
        for row in rows
    )


def role_requires_mapped_entity(role: MappingScopeRuleOperandRole) -> bool:
    return role in (
        MappingScopeRuleOperandRole.SRC_ZONE,
        MappingScopeRuleOperandRole.DST_ZONE,
    )


def status_color_for_mapping_result(
    status: MappingResultStatus | None,
) -> StatusStyleColor:
    if status == MappingResultStatus.MATCHED:
        return StatusStyleColor.GREEN
    if status in (MappingResultStatus.AMBIGUOUS, MappingResultStatus.UNRESOLVED):
        return StatusStyleColor.YELLOW
    return StatusStyleColor.GRAY


def status_color_for_rule(status: MappedRuleStatus) -> StatusStyleColor:
    if status == MappedRuleStatus.MAPPED:
        return StatusStyleColor.GREEN
    if status in (MappedRuleStatus.PARTIAL, MappedRuleStatus.AMBIGUOUS):
        return StatusStyleColor.YELLOW
    if status == MappedRuleStatus.UNRESOLVED:
        return StatusStyleColor.YELLOW
    return StatusStyleColor.GRAY
