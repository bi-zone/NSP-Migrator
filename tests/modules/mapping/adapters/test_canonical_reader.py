from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from app.modules.canonical.application.dto import (
    CanonicalObjectDTO,
    CanonicalRuleDTO,
    CanonicalRuleOperandDTO,
    CanonicalZoneDTO,
    PaginationDTO,
)
from app.modules.canonical.application.use_cases.get_canonical_object import (
    GetCanonicalObjectResult,
)
from app.modules.canonical.application.use_cases.get_canonical_rule_scope import (
    GetCanonicalRuleScopeResult,
)
from app.modules.canonical.domain.enums import ObjectFamily, ObjectKind, OperandRole
from app.modules.mapping.adapters.canonical_reader import CanonicalReader
from app.modules.mapping.domain.exceptions import (
    MappingModuleError,
    MappingModuleNotFoundError,
)
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalAddrObjKind,
    CanonicalRuleAction,
    CanonicalRuleOperandRole,
    CanonicalServiceKind,
)


def _object(
    *,
    family: ObjectFamily,
    kind: ObjectKind,
    object_id: UUID | None = None,
) -> CanonicalObjectDTO:
    return CanonicalObjectDTO(
        id=object_id or uuid4(),
        canonical_snapshot_id=uuid4(),
        object_key="object-key",
        object_family=family,
        object_kind=kind,
        name="object",
        cidr="192.0.2.10/32" if family == ObjectFamily.ADDR else None,
        protocol="tcp" if family == ObjectFamily.SERVICE else None,
        port_from=443 if family == ObjectFamily.SERVICE else None,
        port_to=443 if family == ObjectFamily.SERVICE else None,
    )


@dataclass
class _RuleScopeUseCaseFake:
    result: GetCanonicalRuleScopeResult
    query: object | None = None

    async def execute(self, query: object) -> GetCanonicalRuleScopeResult:
        self.query = query
        return self.result


@dataclass
class _CanonicalObjectUseCaseFake:
    result: GetCanonicalObjectResult | None = None
    error: Exception | None = None

    async def execute(self, query: object) -> GetCanonicalObjectResult:
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def _scope_result(
    *,
    rules: list[CanonicalRuleDTO],
    zones: list[CanonicalZoneDTO],
    objects: list[CanonicalObjectDTO],
) -> GetCanonicalRuleScopeResult:
    return GetCanonicalRuleScopeResult(
        rules=rules,
        zones=zones,
        objects=objects,
        pagination=PaginationDTO(limit=None, offset=None, total=len(rules)),
    )


@pytest.mark.asyncio
async def test_canonical_reader_maps_scope_entities_and_rule_operands() -> None:
    snapshot_id = uuid4()
    rule_id = uuid4()
    zone = CanonicalZoneDTO(
        id=uuid4(),
        canonical_snapshot_id=snapshot_id,
        zone_key="inside",
        name="Inside",
    )
    address = _object(family=ObjectFamily.ADDR, kind=ObjectKind.HOST)
    service = _object(family=ObjectFamily.SERVICE, kind=ObjectKind.TCP)
    rule = CanonicalRuleDTO(
        id=rule_id,
        canonical_snapshot_id=snapshot_id,
        rule_key="allow-https",
        name="Allow HTTPS",
        action="PERMIT",
        enabled=True,
        priority=1,
        operands=[
            CanonicalRuleOperandDTO(
                id=uuid4(),
                rule_id=rule_id,
                operand_role=OperandRole.SRC_ZONE,
                target_zone_id=zone.id,
                target_object_id=None,
                position=1,
            ),
            CanonicalRuleOperandDTO(
                id=uuid4(),
                rule_id=rule_id,
                operand_role=OperandRole.SRC_OBJECT,
                target_zone_id=None,
                target_object_id=address.id,
                position=2,
            ),
            CanonicalRuleOperandDTO(
                id=uuid4(),
                rule_id=rule_id,
                operand_role=OperandRole.SERVICE,
                target_zone_id=None,
                target_object_id=service.id,
                position=3,
            ),
        ],
    )
    scope_use_case = _RuleScopeUseCaseFake(
        _scope_result(rules=[rule], zones=[zone], objects=[address, service])
    )
    reader = CanonicalReader(
        get_canonical_rules_scope=scope_use_case,  # type: ignore[arg-type]
        get_canonical_object=_CanonicalObjectUseCaseFake(),  # type: ignore[arg-type]
    )

    entities = await reader.get_canonical_scope_entities_data(snapshot_id, [rule_id])
    rules = await reader.get_canonical_scope_rules(snapshot_id, [rule_id])

    assert entities.zones[0].zone_key == "inside"
    assert entities.addr_objects[0].kind == CanonicalAddrObjKind.HOST
    assert entities.services[0].kind == CanonicalServiceKind.TCP
    assert rules[0].action == CanonicalRuleAction.PERMIT
    assert rules[0].priority == 1
    assert [operand.role for operand in rules[0].operands] == [
        CanonicalRuleOperandRole.SRC_ZONE,
        CanonicalRuleOperandRole.SRC_OBJECT,
        CanonicalRuleOperandRole.SERVICE,
    ]
    assert scope_use_case.query.filters.rule_ids == [rule_id]  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_canonical_reader_rejects_empty_or_partially_found_rule_request() -> None:
    reader = CanonicalReader(
        get_canonical_rules_scope=_RuleScopeUseCaseFake(
            _scope_result(rules=[], zones=[], objects=[])
        ),  # type: ignore[arg-type]
        get_canonical_object=_CanonicalObjectUseCaseFake(),  # type: ignore[arg-type]
    )

    with pytest.raises(MappingModuleError, match="rules ids"):
        await reader.get_canonical_scope_entities_data(uuid4(), [])

    with pytest.raises(MappingModuleNotFoundError, match="No found canonical rules"):
        await reader.get_canonical_scope_entities_data(uuid4(), [uuid4()])


@pytest.mark.asyncio
async def test_canonical_reader_preserves_object_family_boundary() -> None:
    canonical_object = _object(family=ObjectFamily.SERVICE, kind=ObjectKind.TCP)
    reader = CanonicalReader(
        get_canonical_rules_scope=_RuleScopeUseCaseFake(
            _scope_result(rules=[], zones=[], objects=[])
        ),  # type: ignore[arg-type]
        get_canonical_object=_CanonicalObjectUseCaseFake(
            GetCanonicalObjectResult(object=canonical_object, members=[])
        ),  # type: ignore[arg-type]
    )

    service = await reader.get_canonical_service(uuid4(), canonical_object.id)

    assert service is not None
    assert service.kind == CanonicalServiceKind.TCP
    with pytest.raises(MappingModuleNotFoundError, match="not ADDR"):
        await reader.get_canonical_addr_object(uuid4(), canonical_object.id)
