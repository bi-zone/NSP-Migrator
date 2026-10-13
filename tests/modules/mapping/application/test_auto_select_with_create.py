from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from app.modules.mapping.application.auto_select_with_auto_create import (
    AutoSelectEntitiesWithCreateForScopeCommand,
    AutoSelectEntitiesWithCreateForScopeUseCase,
)
from app.modules.mapping.application.refresh_mapping_scope_catalog_fingerprint import (
    RefreshMappingScopeCatalogFingerprintResult,
)
from app.modules.mapping.domain.entities import MappingEntityResult, MappingScope
from app.modules.mapping.domain.enums import (
    MappingEntityType,
    MappingScopeRulesPriority,
)
from app.modules.mapping.domain.exceptions import MappingModuleNotFoundError


def _scope() -> MappingScope:
    return MappingScope.create_header(
        title="scope",
        canonical_snapshot_id=uuid4(),
        csp_profile_id=uuid4(),
        vpc_id="vpc-1",
        sdwan_target_id="target-1",
        rules_priority=MappingScopeRulesPriority.LOCAL,
        catalog_fingerprint="initial-catalog",
    )


@dataclass
class _RepositoryFake:
    scope: MappingScope | None
    unresolved_results: list[MappingEntityResult]

    async def get_scope_by_id(self, *, scope_id: UUID) -> MappingScope | None:
        if self.scope is None or self.scope.id != scope_id:
            return None
        return self.scope

    async def list_results(self, *, scope_id: UUID, **_: object) -> list[MappingEntityResult]:
        assert self.scope is not None and scope_id == self.scope.id
        return self.unresolved_results


@dataclass
class _SelectWithCreateFake:
    failed_result_id: UUID | None = None
    successful_result_ids: list[UUID] | None = None

    async def execute(self, *, command: object) -> None:
        result_id = command.mapping_result_id  # type: ignore[attr-defined]
        if result_id == self.failed_result_id:
            raise ValueError("cannot create canonical object")
        if self.successful_result_ids is None:
            self.successful_result_ids = []
        self.successful_result_ids.append(result_id)


@dataclass
class _RefreshFingerprintFake:
    result: RefreshMappingScopeCatalogFingerprintResult
    calls: int = 0

    async def execute(
        self, command: object
    ) -> RefreshMappingScopeCatalogFingerprintResult:
        self.calls += 1
        return self.result


@pytest.mark.asyncio
async def test_auto_select_continues_after_failure_and_refreshes_once() -> None:
    scope = _scope()
    first = MappingEntityResult.create_unresolved(
        mapping_scope_id=scope.id,
        entity_type=MappingEntityType.ADDR,
        canonical_entity_id=uuid4(),
    )
    failed = MappingEntityResult.create_unresolved(
        mapping_scope_id=scope.id,
        entity_type=MappingEntityType.SERVICE,
        canonical_entity_id=uuid4(),
    )
    second = MappingEntityResult.create_unresolved(
        mapping_scope_id=scope.id,
        entity_type=MappingEntityType.ADDR,
        canonical_entity_id=uuid4(),
    )
    selector = _SelectWithCreateFake(failed_result_id=failed.id)
    refresh = _RefreshFingerprintFake(
        RefreshMappingScopeCatalogFingerprintResult(
            mapping_scope=scope.refresh_catalog_fingerprint("refreshed-catalog"),
            catalog_fingerprint_changed=True,
        )
    )

    result = await AutoSelectEntitiesWithCreateForScopeUseCase(
        mapping_repo=_RepositoryFake(scope, [first, failed, second]),  # type: ignore[arg-type]
        select_with_create=selector,  # type: ignore[arg-type]
        refresh_mapping_scope_catalog_fingerprint=refresh,  # type: ignore[arg-type]
    ).execute(AutoSelectEntitiesWithCreateForScopeCommand(scope.id))

    assert selector.successful_result_ids == [first.id, second.id]
    assert result.success_selects == 2
    assert result.failed_selects == 1
    assert result.errors == ["cannot create canonical object"]
    assert result.catalog_fingerprint_changed is True
    assert refresh.calls == 1


@pytest.mark.asyncio
async def test_auto_select_returns_zero_counts_without_unresolved_results() -> None:
    scope = _scope()
    refresh = _RefreshFingerprintFake(
        RefreshMappingScopeCatalogFingerprintResult(
            mapping_scope=scope,
            catalog_fingerprint_changed=False,
        )
    )

    result = await AutoSelectEntitiesWithCreateForScopeUseCase(
        mapping_repo=_RepositoryFake(scope, []),  # type: ignore[arg-type]
        select_with_create=_SelectWithCreateFake(),  # type: ignore[arg-type]
        refresh_mapping_scope_catalog_fingerprint=refresh,  # type: ignore[arg-type]
    ).execute(AutoSelectEntitiesWithCreateForScopeCommand(scope.id))

    assert result.success_selects == 0
    assert result.failed_selects == 0
    assert result.errors == []
    assert result.catalog_fingerprint_changed is False
    assert refresh.calls == 0


@pytest.mark.asyncio
async def test_auto_select_requires_mapping_scope() -> None:
    refresh = _RefreshFingerprintFake(
        RefreshMappingScopeCatalogFingerprintResult(
            mapping_scope=_scope(),
            catalog_fingerprint_changed=False,
        )
    )

    with pytest.raises(MappingModuleNotFoundError, match="not found"):
        await AutoSelectEntitiesWithCreateForScopeUseCase(
            mapping_repo=_RepositoryFake(None, []),  # type: ignore[arg-type]
            select_with_create=_SelectWithCreateFake(),  # type: ignore[arg-type]
            refresh_mapping_scope_catalog_fingerprint=refresh,  # type: ignore[arg-type]
        ).execute(AutoSelectEntitiesWithCreateForScopeCommand(uuid4()))
