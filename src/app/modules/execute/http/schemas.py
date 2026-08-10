from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.execute.domain.enums import RuleMatchStatus


class BaseResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
    )


class PreparedExecutePlanResponse(BaseResponseSchema):
    id: UUID
    mapping_scope_id: UUID
    sdwan_target_id: str
    created_at: datetime
    total_rules: int
    new_rules: int
    matched_rules: int
    covered_rules: int
    errors_through_match: int


class PlannedRuleDraftResponse(BaseResponseSchema):
    action: str
    src_zones: list[int]
    dst_zones: list[int]
    src_addr_objects: list[int]
    dst_addr_objects: list[int]
    services: list[int]


class ExecutePlanRuleResponse(BaseResponseSchema):
    id: UUID
    execute_plan_id: UUID
    mapping_scope_rule_id: UUID
    draft: PlannedRuleDraftResponse
    matched_sdwan_rule_id: int | None
    match_status: RuleMatchStatus
    match_info: str


# -- Rules read schemas (duplicated from sdwan integration)
class SdwanRuleAction(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    DROP = "DROP"


class SdwanRuleAddrObject(BaseResponseSchema):
    type: str
    id: int


class SdwanRuleAmbiguousReason(BaseResponseSchema):
    code: int
    meta: dict


class SdwanRuleResponse(BaseResponseSchema):
    type: Literal["policy"]  # ignore null_policy
    policy_id: int
    parents: list[str]
    order: str
    priority: Literal["pre", "local", "post"]
    name: str
    description: str
    tags: list[str]
    activated: bool
    action: SdwanRuleAction
    log: bool
    l4_inspection: bool
    ambiguous: bool
    ambiguous_reason: SdwanRuleAmbiguousReason | None
    created_at: str
    updated_at: str
    snat: dict | None
    dnat: dict | None

    ingress_zone: list[int]
    egress_zone: list[int]

    src_address: list[SdwanRuleAddrObject]
    dst_address: list[SdwanRuleAddrObject]

    service: list[int]

    src_idents: list[Any]
    dst_idents: list[Any]
