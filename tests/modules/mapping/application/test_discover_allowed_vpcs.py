"""Integration-style coverage for allowed VPC discovery.

This test verifies the application-level contract for listing VPCs: the selected
CSP profile id is passed to the SD-WAN gateway provider and the provider's safe
VPC projection is returned unchanged to the caller.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.mapping.application.discover_allowed_vpcs import (
    DiscoverAllowedVpcsQuery,
    DiscoverAllowedVpcsUseCase,
)


@pytest.mark.asyncio
async def test_discover_allowed_vpcs_delegates_to_gateway_provider_with_selected_profile(
    mapping_gateway_provider,
) -> None:
    """Prove VPC discovery is scoped by the user's selected CSP profile id."""
    profile_id = uuid4()
    use_case = DiscoverAllowedVpcsUseCase(mapping_gateway_provider)

    result = await use_case.execute(DiscoverAllowedVpcsQuery(profile_id))

    assert mapping_gateway_provider.discover_calls == [profile_id]
    assert [vpc.vpc_id for vpc in result.vpcs] == ["vpc-1"]
    assert result.vpcs[0].customer_name == "Customer"
