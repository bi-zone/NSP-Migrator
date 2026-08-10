from dataclasses import dataclass

from app.modules.execute.application.dto import SdwanRuleDTO
from app.modules.execute.ports.gateways import ExecuteSDWANGatewayPort


@dataclass(frozen=True, slots=True)
class GetSdwanRulesQuery:
    rules_ids: list[int]


@dataclass(frozen=True, slots=True)
class GetSdwanRulesResult:
    rules: list[SdwanRuleDTO]


class GetSdwanRulesUseCase:
    """Read SD-WAN policy rules by ids for UI display."""

    def __init__(self, sdwan_gateway: ExecuteSDWANGatewayPort) -> None:
        self.sdwan_gateway = sdwan_gateway

    async def execute(self, query: GetSdwanRulesQuery) -> GetSdwanRulesResult:
        """Proxy rule lookup through execute SD-WAN gateway."""
        rules: list[SdwanRuleDTO] = await self.sdwan_gateway.get_rules(query.rules_ids)
        return GetSdwanRulesResult(rules=rules)
