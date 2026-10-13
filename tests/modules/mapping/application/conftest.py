"""Mapping integration-test fixtures for CSP profile binding scenarios.

These fixtures provide fake SD-WAN and canonical-reader boundaries while
allowing mapping use cases to persist their runtime state. They are focused on
verifying that selected CSP profile and VPC identifiers flow into mapping scopes
and gateway acquisition.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import UUID

import pytest

from app.infrastructure.cache import InMemoryTTLStore
from app.integrations.sdwan_csp_api.gateways.enums import SdwanDeviceObjectType
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanDeviceObject,
    SdwanFullCatalog,
)
from app.integrations.sdwan_csp_api.schemas import AllowedVPCResponse
from app.modules.mapping.adapters.runtime_cache import RuntimeCacheMappingRepository
from app.modules.mapping.application.dto import MappingResultsSummary
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalScopeEntities,
)


@dataclass(slots=True)
class RecordingMappingGateway:
    """Fake mapping gateway that returns enough SD-WAN data to start mapping."""

    async def get_device_object(self, dev_obj_id: str) -> SdwanDeviceObject:
        return SdwanDeviceObject(
            dev_obj_id=dev_obj_id,
            name="Selected device",
            type=SdwanDeviceObjectType.DEVICE,
            cpe_id="cpe-1",
        )

    async def get_sdwan_full_catalog(self) -> SdwanFullCatalog:
        return SdwanFullCatalog(zones=[], services=[], addr_objs=[], networks=[])


@dataclass(slots=True)
class RecordingMappingGatewayProvider:
    """Fake provider that records selected profile and VPC acquisition."""

    discover_calls: list[UUID] = field(default_factory=list)
    acquire_calls: list[tuple[UUID, str]] = field(default_factory=list)

    async def discover_vpcs(self, profile_id: UUID) -> list[AllowedVPCResponse]:
        self.discover_calls.append(profile_id)
        return [
            AllowedVPCResponse(
                vpc_id="vpc-1",
                customer_name="Customer",
                project_name="Project",
                cuid="cuid",
                pid="pid",
            )
        ]

    @asynccontextmanager
    async def acquire(
        self,
        profile_id: UUID,
        vpc_id: str,
    ) -> AsyncIterator[RecordingMappingGateway]:
        self.acquire_calls.append((profile_id, vpc_id))
        yield RecordingMappingGateway()


class EmptyCanonicalReader:
    """Fake canonical reader; profile binding tests do not need canonical detail."""

    async def get_canonical_scope_entities_data(
        self,
        *,
        canonical_snapshot_id: UUID,
        canonical_rules_ids: list[UUID],
    ) -> CanonicalScopeEntities:
        return CanonicalScopeEntities(zones=[], addr_objects=[], services=[])

    async def get_canonical_scope_rules(
        self,
        *,
        canonical_snapshot_id: UUID,
        canonical_rules_ids: list[UUID],
    ) -> list:
        return []


class EmptyMappingObjectsService:
    """No-op object mapper used when only scope profile binding is under test."""

    def build_results(
        self, *, mapping_scope_id, canonical_scope_entities, sdwan_full_catalog
    ):
        return []

    def build_results_summary(self, *, results) -> MappingResultsSummary:
        return MappingResultsSummary(
            total_entities=0,
            matched_entities=0,
            ambiguous=0,
            unresolved=0,
            zones_total=0,
            zones_matched=0,
            addr_total=0,
            addr_matched=0,
            services_total=0,
            services_matched=0,
        )


class EmptyMappingScopeRulesBuilder:
    """No-op rule builder used when only scope profile binding is under test."""

    def build(
        self,
        *,
        mapping_scope_id,
        canonical_rules,
        canonical_scope_entities,
        mapping_results,
    ):
        return []


@pytest.fixture
def mapping_repo() -> RuntimeCacheMappingRepository:
    """Create runtime-cache mapping repository for application tests."""
    return RuntimeCacheMappingRepository(
        InMemoryTTLStore(ttl_seconds=60, max_entries=100)
    )


@pytest.fixture
def mapping_gateway_provider() -> RecordingMappingGatewayProvider:
    """Return a fake provider that records VPC discovery and gateway acquisition."""
    return RecordingMappingGatewayProvider()


@pytest.fixture
def empty_canonical_reader() -> EmptyCanonicalReader:
    """Return a fake canonical reader for profile-binding focused scenarios."""
    return EmptyCanonicalReader()


@pytest.fixture
def empty_mapping_objects_service() -> EmptyMappingObjectsService:
    """Return a no-op object mapping service for profile-binding tests."""
    return EmptyMappingObjectsService()


@pytest.fixture
def empty_mapping_scope_rules_builder() -> EmptyMappingScopeRulesBuilder:
    """Return a no-op mapped rule builder for profile-binding tests."""
    return EmptyMappingScopeRulesBuilder()
