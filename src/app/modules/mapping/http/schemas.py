from datetime import datetime
from enum import StrEnum
from ipaddress import IPv4Address, IPv4Network
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MappedCatalogEntityRole(StrEnum):
    SRC_ZONE = "src_zone"
    DST_ZONE = "dst_zone"
    SRC_OBJECT = "src_object"
    DST_OBJECT = "dst_object"
    SERVICE = "service"


class BaseResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
    )


class MappingResultsSummaryResponseSchema(BaseResponseSchema):
    total_entities: int
    matched_entities: int
    ambiguous: int
    unresolved: int
    zones_total: int
    zones_matched: int
    addr_total: int
    addr_matched: int
    services_total: int
    services_matched: int


class MapCanonicalRulesResponseSchema(BaseResponseSchema):
    mapping_scope_id: UUID
    mapping_results_summary: MappingResultsSummaryResponseSchema
    mapped_rules_count: int


# ---------------------------------------------------------------------------
# domain.entities.MappingEntityResult / MappingEntityCandidate schemas
# ---------------------------------------------------------------------------


class MappingEntityCandidateSchema(BaseResponseSchema):
    id: UUID
    result_id: UUID
    rank: int
    score: int
    strategy: str
    sdwan_entity_id: int


class MappingEntityResultSchema(BaseResponseSchema):
    id: UUID
    mapping_scope_id: UUID
    entity_type: str
    canonical_zone_id: UUID | None
    canonical_object_id: UUID | None
    result_status: str
    selection_method: str | None
    selected_sdwan_entity_id: int | None
    created_at: datetime


class MappingEntityResultWithCandidatesSchema(MappingEntityResultSchema):
    candidates: list[MappingEntityCandidateSchema] | None = None


class MappingScopeRuleOperandSchema(BaseResponseSchema):
    id: UUID
    mapping_scope_rule_id: UUID
    role: str
    mapping_entity_result_id: UUID


class MappingScopeRuleSchema(BaseResponseSchema):
    id: UUID
    mapping_scope_id: UUID
    canonical_rule_id: UUID
    name: str
    action: str
    operands: list[MappingScopeRuleOperandSchema] | None = None


class AssignZoneForScopeResponseSchema(BaseResponseSchema):
    mapping_result: MappingEntityResultSchema
    operands: list[MappingScopeRuleOperandSchema]


class AutoSelectWithCreateResponseSchema(BaseResponseSchema):
    failed_selects: int
    success_selects: int
    errors: list[str]


# SD-WAN catalog response schemas
# ---------------------------------------------------------------------------
class SdwanZoneResponseSchema(BaseResponseSchema):
    id: int
    zone_id: int | None = None
    name: str
    type: str


class SdwanServiceResponseSchema(BaseResponseSchema):
    id: int
    name: str
    l4_proto: str
    ranges: list[tuple[int, int]] | tuple[tuple[int, int], ...] | None = None
    codes: list[str] | tuple[str, ...] | None = None


class SdwanAddrObjectResponseSchema(BaseResponseSchema):
    id: int
    parents: list[int] | tuple[int, ...] | None = None
    name: str
    type: str
    network: IPv4Network | None = None
    prefix: IPv4Network | None = None
    host: IPv4Address | None = None
    fqdn: str | None = None
    ip_range_from: IPv4Address | None = None
    ip_range_to: IPv4Address | None = None


class SdwanAddrObjectsResponseSchema(BaseResponseSchema):
    addr_objects: list[SdwanAddrObjectResponseSchema]


class SdwanTargetResponse(BaseResponseSchema):
    dev_obj_id: str
    name: str
    cpe_id: str | None
