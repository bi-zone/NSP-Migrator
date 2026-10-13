from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest

from app.integrations.sdwan_csp_api.schemas import AllowedVPCResponse
from app.modules.reports.application.use_cases.save_report import (
    SaveReportCommand,
    SaveReportRuleCommand,
    SaveReportUseCase,
)
from app.modules.reports.domain.enums import (
    ReportRuleAction,
    ReportRuleMigrationResult,
)
from app.modules.reports.domain.exceptions import ReportsModuleNotFoundError


class _Uow:
    def __init__(self) -> None:
        self.session = None

    async def __aenter__(self) -> _Uow:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False

    def __call__(self, reuse_session: bool = False) -> _Uow:
        return self

    async def commit(self) -> None:
        pass


class _GatewayProvider:
    def __init__(
        self,
        *,
        vpcs: list[AllowedVPCResponse] | None = None,
        gateway: object | None = None,
    ) -> None:
        self.discovered_profile_ids: list[UUID] = []
        self.acquire_calls = 0
        self.vpcs = vpcs or []
        self.gateway = gateway or object()

    async def discover_vpcs(self, profile_id: UUID) -> list[AllowedVPCResponse]:
        self.discovered_profile_ids.append(profile_id)
        return self.vpcs

    @asynccontextmanager
    async def acquire(self, profile_id: UUID, vpc_id: str):
        self.acquire_calls += 1
        yield self.gateway


class _MissingTargetGateway:
    def __init__(self) -> None:
        self.target_ids: list[str] = []
        self.catalog_calls = 0

    async def get_target(self, target_id: str) -> None:
        self.target_ids.append(target_id)
        return None

    async def get_sdwan_full_catalog(self) -> None:
        self.catalog_calls += 1
        raise AssertionError("catalog must not be loaded when target is absent")


def _command(*, profile_id: UUID) -> SaveReportCommand:
    return SaveReportCommand(
        scope_title="Branch migration",
        csp_profile_id=profile_id,
        vpc_id="missing-vpc",
        target_id="target-1",
        commit_id=42,
        rules=(
            SaveReportRuleCommand(
                policy_name="allow-web",
                action=ReportRuleAction.ACCEPT,
                priority=10,
                src_zone_ids=(),
                dst_zone_ids=(),
                src_addr_object_ids=(),
                dst_addr_object_ids=(),
                service_ids=(),
                migration_result=ReportRuleMigrationResult.PUSHED,
                reason="Success",
            ),
        ),
    )


@pytest.mark.asyncio
async def test_save_report_rejects_unknown_vpc_before_acquiring_gateway() -> None:
    profile_id = uuid4()
    gateway_provider = _GatewayProvider()
    use_case = SaveReportUseCase(
        _Uow(),  # type: ignore[arg-type]
        gateway_provider,  # type: ignore[arg-type]
    )

    with pytest.raises(ReportsModuleNotFoundError, match="missing-vpc"):
        await use_case.execute(_command(profile_id=profile_id))

    assert gateway_provider.discovered_profile_ids == [profile_id]
    assert gateway_provider.acquire_calls == 0


@pytest.mark.asyncio
async def test_save_report_rejects_unknown_target_without_loading_catalog() -> None:
    profile_id = uuid4()
    missing_target_gateway = _MissingTargetGateway()
    gateway_provider = _GatewayProvider(
        vpcs=[
            AllowedVPCResponse(
                vpc_id="missing-vpc",
                customer_name="Customer",
                project_name="Project",
                cuid="cuid-1",
                pid="pid-1",
            )
        ],
        gateway=missing_target_gateway,
    )
    use_case = SaveReportUseCase(
        _Uow(),  # type: ignore[arg-type]
        gateway_provider,  # type: ignore[arg-type]
    )

    with pytest.raises(ReportsModuleNotFoundError, match="target-1"):
        await use_case.execute(_command(profile_id=profile_id))

    assert gateway_provider.acquire_calls == 1
    assert missing_target_gateway.target_ids == ["target-1"]
    assert missing_target_gateway.catalog_calls == 0
