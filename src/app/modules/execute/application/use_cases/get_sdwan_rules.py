from dataclasses import dataclass
from uuid import UUID

from app.modules.execute.application.dto import SdwanRuleDTO
from app.modules.execute.ports.gateways import ExecuteSDWANGatewayProviderPort
from app.modules.execute.ports.mapping_reader.port import MappingReaderPort


@dataclass(frozen=True, slots=True)
class GetSdwanRulesQuery:
    mapping_scope_id: UUID
    rules_ids: list[int]


@dataclass(frozen=True, slots=True)
class GetSdwanRulesResult:
    rules: list[SdwanRuleDTO]


class GetSdwanRulesUseCase:
    """Read SD-WAN policy rules by ids for UI display."""

    def __init__(
        self,
        sdwan_gateway_provider: ExecuteSDWANGatewayProviderPort,
        mapping_reader: MappingReaderPort,
    ) -> None:
        self.sdwan_gateway_provider = sdwan_gateway_provider
        self.mapping_reader = mapping_reader

    async def execute(self, query: GetSdwanRulesQuery) -> GetSdwanRulesResult:
        """Proxy rule lookup through execute SD-WAN gateway."""
        scope = await self.mapping_reader.get_mapping_scope_data(query.mapping_scope_id)
        async with self.sdwan_gateway_provider.acquire(
            scope.csp_profile_id,
            scope.vpc_id,
        ) as sdwan_gateway:
            rules: list[SdwanRuleDTO] = await sdwan_gateway.get_rules(query.rules_ids)
        return GetSdwanRulesResult(rules=rules)
