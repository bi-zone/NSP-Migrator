"""Canonical rule read endpoints including rule_scope projection."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.modules.canonical.application.use_cases.get_canonical_rule import (
    GetCanonicalRuleQuery,
    GetCanonicalRuleUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_rule_scope import (
    GetCanonicalRuleScopeQuery,
    GetCanonicalRuleScopeUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_rules import (
    GetCanonicalRulesQuery,
    GetCanonicalRulesUseCase,
)
from app.modules.canonical.di.dependencies import (
    get_canonical_rule_scope_use_case,
    get_canonical_rule_use_case,
    get_canonical_rules_use_case,
)
from app.modules.canonical.http.schemas import (
    CanonicalRuleCoreResponse,
    CanonicalRuleDetailResponse,
    CanonicalRuleOperandHydratedResponse,
    CanonicalRuleResponse,
    CanonicalRuleScopeResponse,
)
from app.modules.canonical.ports.rule_repository import CanonicalRuleFilters

router = APIRouter(tags=["canonical"])


@router.get(
    "/snapshots/{snapshot_id}/rules",
    response_model=list[CanonicalRuleResponse],
    summary="List snapshot rules",
    description=(
        "Returns all rules for a canonical snapshot with flat operand references. "
        "For hydrated zone/object names use the rule detail endpoint. "
        "Returns 404 when the snapshot does not exist."
    ),
)
async def get_snapshot_rules(
    snapshot_id: UUID,
    use_case: GetCanonicalRulesUseCase = Depends(get_canonical_rules_use_case),
) -> list[CanonicalRuleResponse]:
    result = await use_case.execute(
        GetCanonicalRulesQuery(canonical_snapshot_id=snapshot_id)
    )
    return [
        CanonicalRuleResponse.model_validate(rule, from_attributes=True)
        for rule in result.rules
    ]


@router.get(
    "/snapshots/{snapshot_id}/rules/{rule_id}",
    response_model=CanonicalRuleDetailResponse,
    summary="Get snapshot rule with hydrated operands",
    description=(
        "Returns rule metadata plus operands with resolved zone and object summaries. "
        "Used by Streamlit rule inspection. Returns 404 when the snapshot or rule "
        "does not exist."
    ),
)
async def get_snapshot_rule(
    snapshot_id: UUID,
    rule_id: UUID,
    use_case: GetCanonicalRuleUseCase = Depends(get_canonical_rule_use_case),
) -> CanonicalRuleDetailResponse:
    result = await use_case.execute(
        GetCanonicalRuleQuery(canonical_snapshot_id=snapshot_id, rule_id=rule_id)
    )

    rule = result.rule
    operands = rule.operands or []

    return CanonicalRuleDetailResponse(
        rule=CanonicalRuleCoreResponse.model_validate(rule, from_attributes=True),
        operands=[
            CanonicalRuleOperandHydratedResponse.model_validate(
                operand, from_attributes=True
            )
            for operand in operands
        ],
    )


@router.get(
    "/snapshots/{snapshot_id}/rule_scope",
    response_model=CanonicalRuleScopeResponse,
    summary="Get rule scope projection for mapping",
    description=(
        "Primary mapping contract: returns filtered rules plus referenced zones and "
        "objects. Address/service groups are expanded transitively (parent_ids on "
        "objects). When rule filters are active, zones/objects are narrowed to "
        "operands of matching rules unless include_all_zones is true. "
        "Consumed by mapping CanonicalReader and Streamlit. Returns 404 when the "
        "snapshot does not exist."
    ),
)
async def get_snapshot_rule_scope(
    snapshot_id: UUID,
    limit: int | None = Query(
        default=None,
        ge=1,
        le=200,
        description="Page size for rules; omit to return all matching rules.",
    ),
    offset: int | None = Query(
        default=None,
        ge=0,
        description="Row offset for rules pagination; omit to start at zero.",
    ),
    rule_id: list[UUID] | None = Query(
        default=None,
        description="Explicit rule IDs to include in the scope projection.",
    ),
    name_contains: str | None = Query(
        default=None,
        description="Case-sensitive substring match on rule name or rule_key.",
    ),
    action: str | None = Query(
        default=None,
        description="Exact match on rule action (for example permit, deny).",
    ),
    enabled: bool | None = Query(
        default=None,
        description="Filter by rule enabled flag.",
    ),
    section: str | None = Query(
        default=None,
        description="Exact match on ACL section or policy block name.",
    ),
    operand_zone_id: list[UUID] | None = Query(
        default=None,
        description="Rules referencing any of these zone IDs in any operand role.",
    ),
    operand_object_id: list[UUID] | None = Query(
        default=None,
        description="Rules referencing any of these object IDs in any operand role.",
    ),
    include_all_zones: bool = Query(
        default=False,
        description=(
            "When any rule filter is set, return all snapshot zones instead of "
            "only zones referenced by matching rules."
        ),
    ),
    use_case: GetCanonicalRuleScopeUseCase = Depends(get_canonical_rule_scope_use_case),
) -> CanonicalRuleScopeResponse:
    filters = CanonicalRuleFilters(
        rule_ids=list(rule_id) if rule_id else None,
        name_contains=name_contains,
        action=action,
        enabled=enabled,
        section=section,
        operand_zone_ids=list(operand_zone_id) if operand_zone_id else [],
        operand_object_ids=list(operand_object_id) if operand_object_id else [],
    )

    result = await use_case.execute(
        GetCanonicalRuleScopeQuery(
            canonical_snapshot_id=snapshot_id,
            limit=limit,
            offset=offset,
            filters=filters,
            include_all_zones=include_all_zones,
        )
    )

    return CanonicalRuleScopeResponse.model_validate(result, from_attributes=True)
