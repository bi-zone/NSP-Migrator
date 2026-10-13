from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.execute.domain.enums import (
    CoverageField,
    RuleMatchStatus,
    RulePushStatus,
)


class ExcludedExistingRuleResponse(BaseModel):
    sdwan_rule_id: int
    reason: str


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
    excluded_existing_rules: list[ExcludedExistingRuleResponse]


class PlannedRuleDraftResponse(BaseResponseSchema):
    name: str
    action: str
    src_zones: list[int]
    dst_zones: list[int]
    src_addr_objects: list[int]
    dst_addr_objects: list[int]
    services: list[int]


class CoverageValueResponse(BaseResponseSchema):
    object_id: int
    object_name: str
    value: str


class CoverageDetailResponse(BaseResponseSchema):
    field: CoverageField
    covering_value: CoverageValueResponse
    covered_values: list[CoverageValueResponse]


class ExecutePlanRuleResponse(BaseResponseSchema):
    id: UUID
    execute_plan_id: UUID
    mapping_scope_rule_id: UUID
    priority: int
    draft: PlannedRuleDraftResponse
    matched_sdwan_rule_id: int | None
    match_status: RuleMatchStatus
    match_info: str
    coverage_details: list[CoverageDetailResponse]
    push_status: RulePushStatus
    pushed_sdwan_rule_id: int | None
    push_error: str | None


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


class PushRuleResultResponse(BaseResponseSchema):
    execute_plan_rule_id: UUID
    rule_name: str
    sdwan_rule_id: int | None
    error: str | None


class PushExecutePlanRulesResponse(BaseResponseSchema):
    rules: list[SdwanRuleResponse]
    push_results: list[PushRuleResultResponse]
