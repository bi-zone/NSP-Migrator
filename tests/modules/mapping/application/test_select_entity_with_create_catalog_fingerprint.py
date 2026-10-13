from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from app.infrastructure.cache import InMemoryTTLStore
from app.integrations.sdwan_csp_api.gateways.enums import SdwanServiceL4Proto
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanFullCatalog,
    SdwanService,
)
from app.modules.mapping.adapters.runtime_cache import RuntimeCacheMappingRepository
from app.modules.mapping.application.refresh_mapping_scope_catalog_fingerprint import (
    RefreshMappingScopeCatalogFingerprintCommand,
    RefreshMappingScopeCatalogFingerprintUseCase,
)
from app.modules.mapping.application.select_entity_with_create_on_sdwan import (
    SelectEntityWithCreateOnSdwanCommand,
    SelectEntityWithCreateOnSdwanUseCase,
)
from app.modules.mapping.domain.entities import MappingEntityResult, MappingScope
from app.modules.mapping.domain.enums import (
    MappingEntityType,
    MappingScopeRulesPriority,
)
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalService,
    CanonicalServiceKind,
)


class _CanonicalReaderStub:
    def __init__(self, service: CanonicalService) -> None:
        self._service = service

    async def get_canonical_service(
        self,
        *,
        canonical_snapshot_id: UUID,
        canonical_object_id: UUID,
    ) -> CanonicalService:
        assert canonical_object_id == self._service.id
        return self._service


class _GatewayStub:
    def __init__(self, catalog: SdwanFullCatalog) -> None:
        self.catalog = catalog
        self.create_calls = 0

    async def create_service(self, **kwargs: object) -> SdwanService:
        self.create_calls += 1
        service = SdwanService(
            id=100,
            name="https",
            l4_proto=SdwanServiceL4Proto.TCP,
            ranges=((443, 443),),
            codes=None,
        )
        self.catalog = replace(self.catalog, services=[*self.catalog.services, service])
        return service

    async def get_sdwan_full_catalog(self) -> SdwanFullCatalog:
        return self.catalog


class _GatewayProviderStub:
    def __init__(self, gateway: _GatewayStub) -> None:
        self._gateway = gateway

    @asynccontextmanager
    async def acquire(self, profile_id: UUID, vpc_id: str):
        yield self._gateway


@pytest.mark.asyncio
async def test_auto_created_entity_refreshes_mapping_scope_catalog_baseline() -> None:
    original_catalog = SdwanFullCatalog(
        zones=[],
        services=[],
        addr_objs=[],
        networks=[],
    )
    repository = RuntimeCacheMappingRepository(
        InMemoryTTLStore(ttl_seconds=60, max_entries=10)
    )
    scope = MappingScope.create_header(
        title="scope",
        canonical_snapshot_id=uuid4(),
        csp_profile_id=uuid4(),
        vpc_id="vpc-1",
        sdwan_target_id="target-1",
        rules_priority=MappingScopeRulesPriority.LOCAL,
        catalog_fingerprint=original_catalog.get_fingerprint(),
    )
    canonical_service = CanonicalService(
        id=uuid4(),
        kind=CanonicalServiceKind.TCP,
        name="https",
        protocol="tcp",
        port_from=443,
        port_to=443,
    )
    mapping_result = MappingEntityResult.create_unresolved(
        mapping_scope_id=scope.id,
        entity_type=MappingEntityType.SERVICE,
        canonical_entity_id=canonical_service.id,
    )
    gateway = _GatewayStub(original_catalog)

    await repository.add_scope(scope)
    await repository.add_results(scope.id, [mapping_result])
    use_case = SelectEntityWithCreateOnSdwanUseCase(
        mapping_repo=repository,
        sdwan_gateway_provider=_GatewayProviderStub(gateway),  # type: ignore[arg-type]
        canonical_reader=_CanonicalReaderStub(canonical_service),  # type: ignore[arg-type]
        refresh_mapping_scope_catalog_fingerprint=(
            RefreshMappingScopeCatalogFingerprintUseCase(
                mapping_repo=repository,
                sdwan_gateway_provider=_GatewayProviderStub(gateway),  # type: ignore[arg-type]
            )
        ),
    )

    result = await use_case.execute(
        SelectEntityWithCreateOnSdwanCommand(
            mapping_scope_id=scope.id,
            mapping_result_id=mapping_result.id,
        )
    )

    refreshed_scope = await repository.get_scope_by_id(scope.id)
    assert refreshed_scope is not None
    assert result.mapping_result.selected_sdwan_entity_id == 100
    assert result.catalog_fingerprint_changed is True
    assert (
        refreshed_scope.catalog_fingerprint
        == gateway.catalog.get_fingerprint()
    )
    assert refreshed_scope.catalog_fingerprint != scope.catalog_fingerprint


@pytest.mark.asyncio
async def test_refresh_catalog_fingerprint_reports_unchanged_catalog() -> None:
    catalog = SdwanFullCatalog(zones=[], services=[], addr_objs=[], networks=[])
    repository = RuntimeCacheMappingRepository(
        InMemoryTTLStore(ttl_seconds=60, max_entries=10)
    )
    scope = MappingScope.create_header(
        title="scope",
        canonical_snapshot_id=uuid4(),
        csp_profile_id=uuid4(),
        vpc_id="vpc-1",
        sdwan_target_id="target-1",
        rules_priority=MappingScopeRulesPriority.LOCAL,
        catalog_fingerprint=catalog.get_fingerprint(),
    )
    gateway = _GatewayStub(catalog)
    await repository.add_scope(scope)

    result = await RefreshMappingScopeCatalogFingerprintUseCase(
        mapping_repo=repository,
        sdwan_gateway_provider=_GatewayProviderStub(gateway),  # type: ignore[arg-type]
    ).execute(RefreshMappingScopeCatalogFingerprintCommand(mapping_scope_id=scope.id))

    assert result.mapping_scope.id == scope.id
    assert result.mapping_scope.catalog_fingerprint == scope.catalog_fingerprint
    assert result.catalog_fingerprint_changed is False
