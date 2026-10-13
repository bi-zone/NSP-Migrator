from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.integrations.sdwan_csp_api.gateways.models import SdwanDeviceObject
from app.integrations.sdwan_csp_api.schemas import AllowedVPCResponse
from app.modules.reports.application.services.report_rule_values_resolver import (
    ReportRuleValuesResolver,
)
from app.modules.reports.domain.entities import Report
from app.modules.reports.domain.enums import (
    ReportRuleAction,
    ReportRuleMigrationResult,
)
from app.modules.reports.domain.exceptions import ReportsModuleNotFoundError
from app.modules.reports.domain.value_objects import ReportEnvironmentSnapshot
from app.modules.reports.ports.sdwan_gateway import ReportsSDWANGatewayProviderPort
from app.modules.reports.ports.uow import ReportsUnitOfWorkPort


@dataclass(frozen=True, slots=True)
class SaveReportRuleCommand:
    """Raw Execute rule data to enrich into an immutable report snapshot."""

    policy_name: str
    action: ReportRuleAction
    priority: int
    src_zone_ids: tuple[int, ...]
    dst_zone_ids: tuple[int, ...]
    src_addr_object_ids: tuple[int, ...]
    dst_addr_object_ids: tuple[int, ...]
    service_ids: tuple[int, ...]
    migration_result: ReportRuleMigrationResult
    reason: str


@dataclass(frozen=True, slots=True)
class SaveReportCommand:
    """All data needed to persist one completed Execute report."""

    scope_title: str
    csp_profile_id: UUID
    vpc_id: str
    target_id: str
    commit_id: int
    rules: tuple[SaveReportRuleCommand, ...]


@dataclass(frozen=True, slots=True)
class SaveReportResult:
    report: Report


class SaveReportUseCase:
    """Enrich and persist one immutable report produced by Execute."""

    def __init__(
        self,
        uow: ReportsUnitOfWorkPort,
        sdwan_gateway_provider: ReportsSDWANGatewayProviderPort,
    ) -> None:
        self.uow = uow
        self._sdwan_gateway_provider = sdwan_gateway_provider

    @async_transactional(read_only=False)
    async def execute(self, command: SaveReportCommand) -> SaveReportResult:
        vpc = await self._get_vpc(command)
        async with self._sdwan_gateway_provider.acquire(
            command.csp_profile_id,
            command.vpc_id,
        ) as sdwan_gateway:
            target: SdwanDeviceObject | None = (  # fmt: no
                await sdwan_gateway.get_target(command.target_id)
            )
            if target is None:
                raise ReportsModuleNotFoundError(
                    f"SD-WAN target {command.target_id} not found"
                )
            catalog = await sdwan_gateway.get_sdwan_full_catalog()

        values_resolver = ReportRuleValuesResolver(catalog)
        report = Report.create(
            scope_title=command.scope_title,
            csp_profile_id=command.csp_profile_id,
            commit_id=command.commit_id,
            environment=ReportEnvironmentSnapshot(
                project_name=vpc.project_name,
                vpc_id=vpc.vpc_id,
                target_name=target.name,
                target_id=target.dev_obj_id,
            ),
            rule_snapshots=tuple(
                values_resolver.resolve(rule) for rule in command.rules
            ),
        )

        await self.uow.reports.save_report(report)

        return SaveReportResult(report=report)

    async def _get_vpc(self, command: SaveReportCommand) -> AllowedVPCResponse:
        vpcs = await self._sdwan_gateway_provider.discover_vpcs(command.csp_profile_id)
        vpc = next((vpc for vpc in vpcs if vpc.vpc_id == command.vpc_id), None)
        if vpc is None:
            raise ReportsModuleNotFoundError(
                f"VPC {command.vpc_id} not found for profile {command.csp_profile_id}"
            )
        return vpc
