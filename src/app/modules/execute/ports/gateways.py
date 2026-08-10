from abc import ABC, abstractmethod

from app.modules.execute.application.dto import SdwanRuleDTO
from app.modules.execute.domain.entities import ExecutePlanRule
from app.modules.execute.domain.value_objects import SdwanPolicyCatalog


class ExecuteSDWANGatewayPort(ABC):
    @abstractmethod
    async def get_sdwan_policy_catalog(
        self,
        sdwan_target_id: str,
        *,
        extra_zone_ids: set[int] | None = None,
        extra_service_ids: set[int] | None = None,
        extra_addr_object_ids: set[int] | None = None,
    ) -> SdwanPolicyCatalog: ...

    @abstractmethod
    async def push_rules(
        self,
        sdwan_target_id: str,
        plan_rules: list[ExecutePlanRule],
    ) -> list[int]: ...

    @abstractmethod
    async def get_rules(self, rules_ids: list[int]) -> list[SdwanRuleDTO]: ...
