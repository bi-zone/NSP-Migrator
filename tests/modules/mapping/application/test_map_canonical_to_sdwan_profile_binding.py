"""Integration coverage for profile binding during mapping startup.

The scenario verifies the migration-start contract for mapping: the selected
CSP profile and VPC are used when acquiring an SD-WAN gateway and are persisted
on the created mapping scope so later execute steps can reuse the same binding.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.modules.mapping.application.map_canonical_to_sdwan import (
    MapCanonicalToSdwanCommand,
    MapCanonicalToSdwanUseCase,
)
from app.modules.mapping.domain.enums import MappingScopeRulesPriority


@pytest.mark.asyncio
async def test_map_canonical_to_sdwan_uses_selected_profile_and_persists_scope_binding(
    mapping_repo,
    mapping_gateway_provider,
    empty_canonical_reader,
    empty_mapping_objects_service,
    empty_mapping_scope_rules_builder,
) -> None:
    """Prove mapping startup uses and stores the selected CSP profile/VPC pair."""
    profile_id: UUID = uuid4()
    canonical_snapshot_id: UUID = uuid4()
    command = MapCanonicalToSdwanCommand(
        mapping_scope_title="Migration run",
        csp_profile_id=profile_id,
        vpc_id="vpc-selected",
        sdwan_target_id="device-1",
        rules_priority=MappingScopeRulesPriority.LOCAL,
        canonical_snapshot_id=canonical_snapshot_id,
        canonical_rules_ids=[uuid4()],
    )
    use_case = MapCanonicalToSdwanUseCase(
        mapping_repo,
        sdwan_gateway_provider=mapping_gateway_provider,
        canonical_reader=empty_canonical_reader,
        mapping_objects_service=empty_mapping_objects_service,
        mapping_scope_rules_builder=empty_mapping_scope_rules_builder,
    )

    result = await use_case.execute(command)

    assert mapping_gateway_provider.acquire_calls == [(profile_id, "vpc-selected")]
    scope = await mapping_repo.get_scope_by_id(result.mapping_scope_id)
    assert scope is not None
    assert scope.csp_profile_id == profile_id
    assert scope.vpc_id == "vpc-selected"
    assert scope.sdwan_target_id == "device-1"
    assert scope.rules_priority == MappingScopeRulesPriority.LOCAL
    assert result.mapped_rules_count == 0
