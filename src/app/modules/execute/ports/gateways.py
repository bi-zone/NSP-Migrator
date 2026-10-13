from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from typing import Protocol
from uuid import UUID

from app.integrations.sdwan_csp_api.gateways.enums import SdwanRulePriority
from app.integrations.sdwan_csp_api.gateways.models import SdwanFullCatalog
from app.modules.execute.application.dto import (
    CommitInfoDTO,
    PushRuleResultDTO,
    SdwanRuleDTO,
)
from app.modules.execute.domain.entities import ExecutePlanRule
from app.modules.execute.domain.value_objects import SdwanPolicyCatalog


class ExecuteSDWANGatewayPort(ABC):
    @abstractmethod
    async def get_sdwan_full_catalog(self) -> SdwanFullCatalog: ...

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
        priority: SdwanRulePriority,
    ) -> list[PushRuleResultDTO]: ...

    @abstractmethod
    async def get_rules(self, rules_ids: list[int]) -> list[SdwanRuleDTO]: ...

    @abstractmethod
    async def commit_csp_changes(self) -> CommitInfoDTO: ...


class ExecuteSDWANGatewayProviderPort(Protocol):
    @abstractmethod
    def acquire(
        self,
        profile_id: UUID,
        vpc_id: str,
    ) -> AbstractAsyncContextManager[ExecuteSDWANGatewayPort]: ...
