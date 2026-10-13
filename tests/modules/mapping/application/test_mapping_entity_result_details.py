from contextlib import asynccontextmanager
from ipaddress import IPv4Address
from uuid import UUID, uuid4

import pytest

from app.integrations.sdwan_csp_api.gateways.enums import SdwanAddrObjectType
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
    SdwanFullCatalog,
)
from app.modules.mapping.application.get_mapping_entity_result_details import (
    GetMappingEntityResultDetailsQuery,
    GetMappingEntityResultDetailsUseCase,
)
from app.modules.mapping.domain.entities import MappingEntityResult, MappingScope
from app.modules.mapping.domain.enums import (
    CandidateMatchStrategy,
    MappingEntityType,
    MappingScopeRulesPriority,
)
from app.modules.mapping.domain.exceptions import MappingModuleNotFoundError
from app.modules.mapping.domain.value_objects import MappingEntityCandidatePayload


def _scope() -> MappingScope:
    return MappingScope.create_header(
        title="migration",
        canonical_snapshot_id=uuid4(),
        csp_profile_id=uuid4(),
        vpc_id="vpc-1",
        sdwan_target_id="target-1",
        rules_priority=MappingScopeRulesPriority.POST,
        catalog_fingerprint="catalog",
    )


def _catalog() -> SdwanFullCatalog:
    return SdwanFullCatalog(
        zones=[],
        services=[],
        addr_objs=[
            SdwanAddrObject(
                id=10,
                parents=(),
                name="first-host",
                type=SdwanAddrObjectType.HOST,
                host=IPv4Address("192.0.2.10"),
            ),
            SdwanAddrObject(
                id=20,
                parents=(),
                name="second-host",
                type=SdwanAddrObjectType.HOST,
                host=IPv4Address("192.0.2.20"),
            ),
        ],
        networks=[],
    )


class _RepositoryFake:
    def __init__(
        self,
        *,
        scope: MappingScope | None,
        mapping_result: MappingEntityResult | None,
    ) -> None:
        self._scope = scope
        self._mapping_result = mapping_result
        self.with_candidates: bool | None = None

    async def get_result(
        self,
        *,
        scope_id: UUID,
        result_id: UUID,
        with_candidates: bool,
    ) -> MappingEntityResult | None:
        self.with_candidates = with_candidates
        return self._mapping_result

    async def get_scope_by_id(self, scope_id: UUID) -> MappingScope | None:
        return self._scope


class _GatewayFake:
    async def get_sdwan_full_catalog(self) -> SdwanFullCatalog:
        return _catalog()


class _GatewayProviderFake:
    @asynccontextmanager
    async def acquire(self, profile_id: UUID, vpc_id: str):  # type: ignore[no-untyped-def]
        yield _GatewayFake()


@pytest.mark.asyncio
async def test_details_sorts_ambiguous_candidates_and_keeps_them_unselected() -> None:
    scope = _scope()
    mapping_result = MappingEntityResult.create_ambiguous(
        mapping_scope_id=scope.id,
        entity_type=MappingEntityType.ADDR,
        canonical_entity_id=uuid4(),
        candidates_payloads=[
            MappingEntityCandidatePayload(
                rank=2,
                score=100,
                strategy=CandidateMatchStrategy.EXACT_VALUE,
                sdwan_entity_id=10,
            ),
            MappingEntityCandidatePayload(
                rank=1,
                score=80,
                strategy=CandidateMatchStrategy.NORMALIZED_NAME,
                sdwan_entity_id=20,
            ),
        ],
    )
    repo = _RepositoryFake(scope=scope, mapping_result=mapping_result)
    use_case = GetMappingEntityResultDetailsUseCase(
        mapping_repo=repo,  # type: ignore[arg-type]
        sdwan_gateway_provider=_GatewayProviderFake(),  # type: ignore[arg-type]
    )

    result = await use_case.execute(
        GetMappingEntityResultDetailsQuery(
            mapping_scope_id=scope.id,
            mapping_result_id=mapping_result.id,
        )
    )

    assert repo.with_candidates is True
    assert result.details.selected_sdwan is None
    assert [candidate.sdwan_id for candidate in result.details.candidates] == [20, 10]
    assert result.details.candidates[0].str_value == "192.0.2.20"


@pytest.mark.asyncio
async def test_details_resolves_selected_sdwan_entity_for_matched_result() -> None:
    scope = _scope()
    mapping_result = MappingEntityResult.create_matched_auto(
        mapping_scope_id=scope.id,
        entity_type=MappingEntityType.ADDR,
        canonical_entity_id=uuid4(),
        candidate_payload=MappingEntityCandidatePayload(
            rank=1,
            score=100,
            strategy=CandidateMatchStrategy.EXACT_VALUE,
            sdwan_entity_id=10,
        ),
    )
    use_case = GetMappingEntityResultDetailsUseCase(
        mapping_repo=_RepositoryFake(scope=scope, mapping_result=mapping_result),  # type: ignore[arg-type]
        sdwan_gateway_provider=_GatewayProviderFake(),  # type: ignore[arg-type]
    )

    result = await use_case.execute(
        GetMappingEntityResultDetailsQuery(scope.id, mapping_result.id)
    )

    assert result.details.selected_sdwan is not None
    assert result.details.selected_sdwan.sdwan_id == 10
    assert result.details.selected_sdwan.str_value == "192.0.2.10"


@pytest.mark.asyncio
async def test_details_rejects_missing_mapping_result_before_loading_catalog() -> None:
    scope = _scope()
    result_id = uuid4()
    use_case = GetMappingEntityResultDetailsUseCase(
        mapping_repo=_RepositoryFake(scope=scope, mapping_result=None),  # type: ignore[arg-type]
        sdwan_gateway_provider=None,  # type: ignore[arg-type]
    )

    with pytest.raises(MappingModuleNotFoundError, match=str(result_id)):
        await use_case.execute(GetMappingEntityResultDetailsQuery(scope.id, result_id))
