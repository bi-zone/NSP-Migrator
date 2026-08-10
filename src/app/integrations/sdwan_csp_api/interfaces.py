from enum import StrEnum
from typing import Any, Protocol, TypeAlias

from app.integrations.sdwan_csp_api.schemas import (
    AddrObjectResponse,
    ApplyCommitResultResponse,
    CommitEntityDto,
    CPEInfoResponse,
    CreateAddrObjectRequest,
    CreatePolicyRequest,
    DeviceObjectResponse,
    NetworkResponse,
    PolicyResponse,
    ServiceCreateRequest,
    ServiceResponse,
    ZoneResponse,
)

SDWANCspHttpJsonPrimitive: TypeAlias = str | int | float | bool | None
SDWANCspHttpJsonValue: TypeAlias = (
    SDWANCspHttpJsonPrimitive
    | dict[str, "SDWANCspHttpJsonValue"]
    | list["SDWANCspHttpJsonValue"]
)


class SDWANHttpMethod(StrEnum):
    GET = "GET"
    POST = "POST"


class ISDWANCspHttpClient(Protocol):
    async def health_check(self) -> None: ...

    async def authorized_request(
        self,
        *,
        method: SDWANHttpMethod,
        path: str,
        params: dict[str, Any] | None = None,
        json: SDWANCspHttpJsonValue | None = None,
    ) -> SDWANCspHttpJsonValue: ...

    async def get_vpc_id(self) -> str: ...

    # -- API methods
    async def commit_rule_objects(
        self,
        commit_name: str,
        commit_description: str,
        entities: list[CommitEntityDto],
    ) -> int: ...

    async def get_commit_info(self, commit_id: int) -> dict:
        """Get commit info and linked diffs"""
        ...

    async def get_commit_diffs_info(self, commit_id: int) -> dict: ...

    async def apply_commit(self, commit_id: int) -> ApplyCommitResultResponse: ...

    async def get_zones(
        self,
        ids: list[int] | None = None,
        limit: int | None = None,
    ) -> list[ZoneResponse]: ...

    async def get_services(
        self,
        ids: list[int] | None = None,
        limit: int | None = None,
    ) -> list[ServiceResponse]: ...

    async def get_addr_objects(
        self,
        ids: list[int] | None = None,
        limit: int | None = None,
        without_parents: bool = False,
    ) -> list[AddrObjectResponse]: ...

    async def get_addr_objects_by_parents_ids(
        self,
        parents_ids: list[int],
    ) -> list[AddrObjectResponse]: ...

    async def get_networks(
        self,
        network_ids: list[str] | None = None,
        limit: int | None = None,
    ) -> list[NetworkResponse]: ...

    async def create_addr_objects(
        self, payloads: list[CreateAddrObjectRequest]
    ) -> list[int]: ...

    async def create_service(
        self, payload: ServiceCreateRequest
    ) -> ServiceResponse: ...

    async def get_cpe_info(self, cpe_id: str) -> CPEInfoResponse: ...

    async def get_device_objects(
        self, dev_obj_id: str | None = None
    ) -> list[DeviceObjectResponse]: ...

    async def get_policies(
        self, dev_obj_id: str | None = None
    ) -> list[PolicyResponse]: ...

    async def create_policy(self, payload: CreatePolicyRequest) -> int: ...

    async def get_policies_by_ids(
        self,
        ids: list[int],
    ) -> list[PolicyResponse]: ...
