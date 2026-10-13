from uuid import UUID, uuid4

import pytest

from app.modules.mapping.domain.entities import MappingEntityResult
from app.modules.mapping.domain.enums import (
    CandidateMatchStrategy,
    MappingEntityType,
    MappingScopeRuleAction,
    MappingScopeRuleOperandRole,
)
from app.modules.mapping.domain.exceptions import MappingModuleDomainValidationError
from app.modules.mapping.domain.value_objects import MappingEntityCandidatePayload
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalAddrObject,
    CanonicalAddrObjKind,
    CanonicalRule,
    CanonicalRuleAction,
    CanonicalRuleOperand,
    CanonicalRuleOperandRole,
    CanonicalScopeEntities,
    CanonicalService,
    CanonicalServiceKind,
    CanonicalZone,
)
from app.modules.mapping.services.mapping_rules.mapping_scope_rules_builder import (
    MappingScopeRulesBuilder,
)


def _matched_result(
    *,
    scope_id: UUID,
    entity_type: MappingEntityType,
    canonical_entity_id: UUID,
    sdwan_id: int,
) -> MappingEntityResult:
    return MappingEntityResult.create_matched_auto(
        mapping_scope_id=scope_id,
        entity_type=entity_type,
        canonical_entity_id=canonical_entity_id,
        candidate_payload=MappingEntityCandidatePayload(
            rank=1,
            score=100,
            strategy=CandidateMatchStrategy.EXACT_VALUE,
            sdwan_entity_id=sdwan_id,
        ),
    )


def test_builder_expands_groups_and_links_every_operand_to_mapping_result() -> None:
    scope_id = uuid4()
    rule_id = uuid4()
    source_zone = CanonicalZone(id=uuid4(), zone_key="source", name="Source")
    destination_zone = CanonicalZone(
        id=uuid4(), zone_key="destination", name="Destination"
    )
    source_address = CanonicalAddrObject(
        id=uuid4(), kind=CanonicalAddrObjKind.HOST, name="source"
    )
    destination_group = CanonicalAddrObject(
        id=uuid4(), kind=CanonicalAddrObjKind.ADDR_GROUP, name="destination-group"
    )
    destination_host = CanonicalAddrObject(
        id=uuid4(),
        kind=CanonicalAddrObjKind.HOST,
        name="destination-host",
        parent_ids=(destination_group.id,),
    )
    service_group = CanonicalService(
        id=uuid4(), kind=CanonicalServiceKind.SERVICE_GROUP, name="web-services"
    )
    https = CanonicalService(
        id=uuid4(),
        kind=CanonicalServiceKind.TCP,
        name="https",
        parent_ids=(service_group.id,),
        protocol="tcp",
        port_from=443,
        port_to=443,
    )
    entities = CanonicalScopeEntities(
        zones=[source_zone, destination_zone],
        addr_objects=[source_address, destination_group, destination_host],
        services=[service_group, https],
    )
    results = [
        _matched_result(
            scope_id=scope_id,
            entity_type=MappingEntityType.ZONE,
            canonical_entity_id=source_zone.id,
            sdwan_id=1,
        ),
        _matched_result(
            scope_id=scope_id,
            entity_type=MappingEntityType.ZONE,
            canonical_entity_id=destination_zone.id,
            sdwan_id=2,
        ),
        _matched_result(
            scope_id=scope_id,
            entity_type=MappingEntityType.ADDR,
            canonical_entity_id=source_address.id,
            sdwan_id=10,
        ),
        _matched_result(
            scope_id=scope_id,
            entity_type=MappingEntityType.ADDR,
            canonical_entity_id=destination_host.id,
            sdwan_id=20,
        ),
        _matched_result(
            scope_id=scope_id,
            entity_type=MappingEntityType.SERVICE,
            canonical_entity_id=https.id,
            sdwan_id=100,
        ),
    ]
    rule = CanonicalRule(
        id=rule_id,
        canonical_snapshot_id=uuid4(),
        name="Allow HTTPS",
        action=CanonicalRuleAction.PERMIT,
        priority=10,
        operands=[
            CanonicalRuleOperand(
                id=uuid4(),
                rule_id=rule_id,
                role=CanonicalRuleOperandRole.SRC_ZONE,
                target_zone_id=source_zone.id,
                target_object_id=None,
            ),
            CanonicalRuleOperand(
                id=uuid4(),
                rule_id=rule_id,
                role=CanonicalRuleOperandRole.DST_ZONE,
                target_zone_id=destination_zone.id,
                target_object_id=None,
            ),
            CanonicalRuleOperand(
                id=uuid4(),
                rule_id=rule_id,
                role=CanonicalRuleOperandRole.SRC_OBJECT,
                target_zone_id=None,
                target_object_id=source_address.id,
            ),
            CanonicalRuleOperand(
                id=uuid4(),
                rule_id=rule_id,
                role=CanonicalRuleOperandRole.DST_OBJECT,
                target_zone_id=None,
                target_object_id=destination_group.id,
            ),
            CanonicalRuleOperand(
                id=uuid4(),
                rule_id=rule_id,
                role=CanonicalRuleOperandRole.SERVICE,
                target_zone_id=None,
                target_object_id=service_group.id,
            ),
        ],
    )

    mapped_rule = MappingScopeRulesBuilder().build(
        mapping_scope_id=scope_id,
        canonical_rules=[rule],
        canonical_scope_entities=entities,
        mapping_results=results,
    )[0]

    assert mapped_rule.action == MappingScopeRuleAction.ACCEPT
    assert mapped_rule.priority == 10
    assert [operand.role for operand in mapped_rule.operands or []] == [
        MappingScopeRuleOperandRole.SRC_ZONE,
        MappingScopeRuleOperandRole.DST_ZONE,
        MappingScopeRuleOperandRole.SRC_ADDR_OBJECT,
        MappingScopeRuleOperandRole.DST_ADDR_OBJECT,
        MappingScopeRuleOperandRole.SERVICE,
    ]
    assert {
        operand.mapping_entity_result_id for operand in mapped_rule.operands or []
    } == {result.id for result in results}


def test_builder_rejects_rule_operand_without_mapping_result() -> None:
    scope_id = uuid4()
    zone = CanonicalZone(id=uuid4(), zone_key="source", name="Source")
    rule = CanonicalRule(
        id=uuid4(),
        canonical_snapshot_id=uuid4(),
        name="Missing mapping result",
        action=CanonicalRuleAction.DENY,
        priority=20,
        operands=[
            CanonicalRuleOperand(
                id=uuid4(),
                rule_id=uuid4(),
                role=CanonicalRuleOperandRole.SRC_ZONE,
                target_zone_id=zone.id,
                target_object_id=None,
            )
        ],
    )

    with pytest.raises(MappingModuleDomainValidationError, match="Mapping result"):
        MappingScopeRulesBuilder().build(
            mapping_scope_id=scope_id,
            canonical_rules=[rule],
            canonical_scope_entities=CanonicalScopeEntities(
                zones=[zone], addr_objects=[], services=[]
            ),
            mapping_results=[],
        )
