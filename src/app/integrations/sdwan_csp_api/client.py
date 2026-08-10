from enum import StrEnum
from typing import Any

from pydantic import ValidationError

from app.infrastructure.interfaces.http_requester import (
    HttpMethod,
    HttpRequestTimeoutError,
    HttpRequestTransportError,
    HttpResponseStatusError,
    IAsyncHttpRequester,
)
from app.integrations.sdwan_csp_api.exceptions import (
    SDWANCspHttpAuthError,
    SDWANCspHttpConnectionError,
    SDWANCspHttpError,
    SDWANCspHttpResponseError,
)
from app.integrations.sdwan_csp_api.interfaces import (
    ISDWANCspHttpClient,
    SDWANCspHttpJsonValue,
    SDWANHttpMethod,
)
from app.integrations.sdwan_csp_api.schemas import (
    AddrObjectResponse,
    AddrObjectsResponse,
    ApplyCommitResultResponse,
    CommitEntityDto,
    CommitRuleObjectsRequest,
    CPEInfoResponse,
    CreateAddrObjectRequest,
    CreatePolicyRequest,
    DeviceObjectResponse,
    LoginRequest,
    LoginResponse,
    NetworkResponse,
    NetworksResponse,
    PolicyResponse,
    ServiceCreateRequest,
    ServiceResponse,
    ServicesResponse,
    ZoneResponse,
    ZonesResponse,
)


class SDWANCspHttpClientEndpoints(StrEnum):
    """Base SD-WAN endpoints"""

    HEALTH_CHECK = "/build_version"
    LOGIN = "/us/v1/login"
    COMMITS = "/so/v1/vpcs/{vpc_id}/commits"
    DIFF = "/so/v1/vpcs/{vpc_id}/diff"
    TASKS = "/so/v1/vpcs/{vpc_id}/tasks"
    ZONES = "/ac/v1/zones"
    SERVICES = "/so/v2/vpcs/{vpc_id}/fw/services"
    SERVICES_V1 = "/so/v1/vpcs/{vpc_id}/fw/services"
    ADDR_OBJECTS = "/so/v1/address_objects"
    NETWORKS = "/ac/v1/networks"
    CPE = "/ac/v1/cpes"
    DEVICE_OBJECTS = "/ac/v1/device_objects"
    POLICIES = "/so/v2/policies"


class SDWANCspHttpClient(ISDWANCspHttpClient):
    """API Client for SD-WAN API using.
    Здесь располагаются методы, которые именно провайдят данные из эндпоинтов
    API от SD-WAN, более доменно-сфокусированные методы будут описываться уже в модулях
    в gateway.
    """

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        vpc_id: str,
        requester: IAsyncHttpRequester,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._requester = requester
        self._vpc_id = vpc_id
        self._token: str | None = None
        self._auth_data: Any | None = None

    # -- Internal Tools
    async def _get_auth_headers(self) -> dict[str, str]:
        """Return a dict with auth headers"""
        await self._refresh_auth_data()
        return {"Authorization": f"Bearer {self._token}"}

    async def _refresh_auth_data(self) -> None:
        """Refresh auth data (token, vpc_id)"""
        try:
            payload = LoginRequest(
                user=self._username,
                password=self._password,
                vpc_id=self._vpc_id,
            )
            response = await self._requester.request(
                method=HttpMethod(SDWANHttpMethod.POST),
                url=f"{self._base_url}{SDWANCspHttpClientEndpoints.LOGIN}",
                json=payload.model_dump(),
            )
        except HttpResponseStatusError as exc:
            raise SDWANCspHttpAuthError(
                f"Login to SD-WAN API failed with status {exc.status_code}"
            ) from exc
        except (HttpRequestTransportError, HttpRequestTimeoutError) as exc:
            raise SDWANCspHttpConnectionError(
                "Network error while logging in to SD-WAN API"
            ) from exc

        try:
            serialized_response = LoginResponse.model_validate(response)
        except ValidationError as exc:
            raise SDWANCspHttpResponseError("Invalid login response schema") from exc

        self._auth_data = response
        self._token = serialized_response.token

    # -- Public methods
    async def health_check(self) -> None:
        """Check the health of the SD-WAN API"""
        await self._requester.request(
            method=HttpMethod.GET,
            url=f"{self._base_url}{SDWANCspHttpClientEndpoints.HEALTH_CHECK}",
        )

    async def authorized_request(
        self,
        *,
        method: SDWANHttpMethod,
        path: str,
        params: dict[str, Any] | None = None,
        json: SDWANCspHttpJsonValue | None = None,
    ) -> SDWANCspHttpJsonValue:
        """Make a request to SD-WAN API with auth credentials"""
        headers = await self._get_auth_headers()

        try:
            return await self._requester.request(
                method=HttpMethod(method),
                url=f"{self._base_url}{path}",
                params=params,
                headers=headers,
                json=json,
            )
        except HttpResponseStatusError as exc:
            if exc.status_code in (401, 403):
                self._token = None
                raise SDWANCspHttpAuthError(
                    f"SD-WAN API auth failed with status {exc.status_code}: {exc.response_body}"
                ) from exc
            raise SDWANCspHttpError(
                f"SD-WAN API request failed with status {exc.status_code}: {exc.response_body}"
            ) from exc
        except (HttpRequestTransportError, HttpRequestTimeoutError) as exc:
            raise SDWANCspHttpConnectionError(
                "Network error while calling SD-WAN API"
            ) from exc

    # -- API methods
    @staticmethod
    def _prepare_commit_filter_expr(entities: list[CommitEntityDto]) -> str:
        """Prepare commit filter expression"""
        base_filter_template: str = (
            '(entity_kind = "{ent_kind}" and entity_id = {ent_id})'
        )
        filters_for_expr: list[str] = [
            base_filter_template.format(ent_kind=ent.kind, ent_id=ent.id)
            for ent in entities
        ]
        filter_expr = " or ".join(filters_for_expr)
        return filter_expr

    async def commit_rule_objects(
        self,
        commit_name: str,
        commit_description: str,
        entities: list[CommitEntityDto],
    ) -> int:
        """Commit a list of rule objects. Returns commit object id"""
        filter_expr: str = self._prepare_commit_filter_expr(entities)

        payload = CommitRuleObjectsRequest(
            name=commit_name,
            description=commit_description,
            force=True,
            filter=filter_expr,
        )

        response = await self.authorized_request(
            method=SDWANHttpMethod.POST,
            path=SDWANCspHttpClientEndpoints.COMMITS.format(vpc_id=self._vpc_id),
            json=payload.model_dump(mode="json"),
        )

        if not isinstance(response, int):
            raise TypeError(
                f"Expected integer response from {SDWANCspHttpClientEndpoints.COMMITS}"
            )

        return response

    async def get_commit_info(self, commit_id: int) -> dict:
        """Get commit info and linked diffs"""
        single_commit_info_response = await self.authorized_request(
            method=SDWANHttpMethod.GET,
            path=SDWANCspHttpClientEndpoints.COMMITS.format(vpc_id=self._vpc_id),
            params={"query": f"commit_id = {commit_id}"},
        )
        return single_commit_info_response["data"][0]  # type: ignore

    async def get_commit_diffs_info(self, commit_id: int) -> dict:
        """Get commit info and linked diffs"""
        diffs_info_response = await self.authorized_request(
            method=SDWANHttpMethod.GET,
            path=SDWANCspHttpClientEndpoints.DIFF.format(vpc_id=self._vpc_id),
            params={"for_commit": commit_id},
        )
        return diffs_info_response["data"]  # type: ignore

    async def apply_commit(self, commit_id: int) -> ApplyCommitResultResponse:
        """Apply the commit (sync configs with CPEs)"""
        # TODO: search info about "rollback" for apply process with API
        response = await self.authorized_request(
            method=SDWANHttpMethod.POST,
            path=SDWANCspHttpClientEndpoints.TASKS.format(vpc_id=self._vpc_id),
            json={
                "kind": "apply",
                "payload": {
                    "commit_id": commit_id,
                    "confirm_timeout": None,
                    "filter": None,
                },
            },
        )
        return ApplyCommitResultResponse.model_validate(response)

    async def get_zones(
        self,
        ids: list[int] | None = None,
        limit: int | None = None,
    ) -> list[ZoneResponse]:
        """Get a list of zones"""
        params: dict[str, Any] = {}

        if limit is not None:
            params["limit"] = limit

        if ids:
            params["id"] = ",".join(map(str, ids))

        response = await self.authorized_request(
            method=SDWANHttpMethod.GET,
            path=SDWANCspHttpClientEndpoints.ZONES,
            params=params,
        )

        if limit is None:
            total: int = response["total"]  # type: ignore
            if len(response["result"]) < total:  # type: ignore
                params["limit"] = total
                response = await self.authorized_request(
                    method=SDWANHttpMethod.GET,
                    path=SDWANCspHttpClientEndpoints.ZONES,
                    params=params,
                )

        try:
            serialized_response = ZonesResponse.model_validate(response)
        except ValidationError as exc:
            raise SDWANCspHttpResponseError(
                "Invalid zones response schema" + f"{exc}"
            ) from exc

        return serialized_response.result

    async def get_services(
        self,
        ids: list[int] | None = None,
        limit: int | None = None,
    ) -> list[ServiceResponse]:
        """Get a list of services"""
        params: dict[str, Any] = {}

        if limit is not None:
            params["limit"] = limit

        if ids:
            params["query"] = f"id = ({' '.join(map(str, ids))})"

        path = SDWANCspHttpClientEndpoints.SERVICES.format(vpc_id=self._vpc_id)

        response = await self.authorized_request(
            method=SDWANHttpMethod.GET,
            path=path,
            params=params,
        )

        if limit is None:
            total: int = response["meta"]["total"]  # type: ignore
            if len(response["data"]) < total:  # type: ignore
                params["limit"] = total
                response = await self.authorized_request(
                    method=SDWANHttpMethod.GET,
                    path=path,
                    params=params,
                )

        try:
            serialized_response = ServicesResponse.model_validate(response)
        except ValidationError as exc:
            raise SDWANCspHttpResponseError(
                "Invalid services response schema" + f"{exc}"
            ) from exc

        return serialized_response.data

    async def get_addr_objects(
        self,
        ids: list[int] | None = None,
        limit: int | None = None,
        without_parents: bool = False,
    ) -> list[AddrObjectResponse]:
        """Get a list of addr_objects
        - if "ids" empty - returns all address objects

        Сейчас реализовано с parent = (), то есть возвращает адресные объекты,
        у которых нет родительских связей, то есть самые верхнеуровневые.
        Позже нужно выяснить - нужно ли вытаскивать и такие объекты тоже.
        """
        params: dict[str, Any] = {}

        if limit is not None:
            params["limit"] = limit

        if ids:
            params["query"] = f"id = ({' '.join(map(str, ids))})"

        if without_parents:
            if "query" in params:
                params["query"] += "and parents = ()"
            else:
                params["query"] = "parents = ()"

        response = await self.authorized_request(
            method=SDWANHttpMethod.GET,
            path=SDWANCspHttpClientEndpoints.ADDR_OBJECTS,
            params=params,
        )

        if limit is None:
            total: int = response["meta"]["total"]  # type: ignore
            if len(response["data"]) < total:  # type: ignore
                params["limit"] = total
                response = await self.authorized_request(
                    method=SDWANHttpMethod.GET,
                    path=SDWANCspHttpClientEndpoints.ADDR_OBJECTS,
                    params=params,
                )

        try:
            serialized_response = AddrObjectsResponse.model_validate(response)
        except ValidationError as exc:
            raise SDWANCspHttpResponseError(
                "Invalid addr_objects response schema" + f"{exc}"
            ) from exc

        return serialized_response.data

    async def get_addr_objects_by_parents_ids(
        self,
        parents_ids: list[int],
    ) -> list[AddrObjectResponse]:
        """Get a list of addr_objects that have provided parents ids"""
        queries = [f"parents = ({id_})" for id_ in parents_ids]
        params: dict[str, Any] = {"query": " or ".join(queries)}

        response = await self.authorized_request(
            method=SDWANHttpMethod.GET,
            path=SDWANCspHttpClientEndpoints.ADDR_OBJECTS,
            params=params,
        )

        # to fetch all
        total: int = response["meta"]["total"]  # type: ignore
        if len(response["data"]) < total:  # type: ignore
            params["limit"] = total
            response = await self.authorized_request(
                method=SDWANHttpMethod.GET,
                path=SDWANCspHttpClientEndpoints.ADDR_OBJECTS,
                params=params,
            )

        try:
            serialized_response = AddrObjectsResponse.model_validate(response)
        except ValidationError as exc:
            raise SDWANCspHttpResponseError(
                "Invalid addr_objects response schema" + f"{exc}"
            ) from exc

        return serialized_response.data

    async def get_networks(
        self,
        network_ids: list[str] | None = None,
        limit: int | None = None,
    ) -> list[NetworkResponse]:
        """Get a list of networks"""
        params: dict[str, Any] = {}

        if limit is not None:
            params["limit"] = limit

        if network_ids:
            params["network_id"] = ",".join(network_ids)

        response = await self.authorized_request(
            method=SDWANHttpMethod.GET,
            path=SDWANCspHttpClientEndpoints.NETWORKS,
            params=params,
        )

        if limit is None:
            total: int = response["total"]  # type: ignore
            if len(response["result"]) < total:  # type: ignore
                params["limit"] = total
                response = await self.authorized_request(
                    method=SDWANHttpMethod.GET,
                    path=SDWANCspHttpClientEndpoints.NETWORKS,
                    params=params,
                )

        try:
            serialized_response = NetworksResponse.model_validate(response)
        except ValidationError as exc:
            raise SDWANCspHttpResponseError(
                "Invalid zones response schema" + f"{exc}"
            ) from exc

        return serialized_response.result

    async def create_addr_objects(
        self, payloads: list[CreateAddrObjectRequest]
    ) -> list[int]:
        """Create address objects"""
        response = await self.authorized_request(
            method=SDWANHttpMethod.POST,
            path=SDWANCspHttpClientEndpoints.ADDR_OBJECTS,
            json=[p.model_dump(mode="json") for p in payloads],
        )
        return response  # type: ignore

    async def create_service(self, payload: ServiceCreateRequest) -> ServiceResponse:
        """Create service"""
        path = SDWANCspHttpClientEndpoints.SERVICES_V1.format(vpc_id=self._vpc_id)

        response = await self.authorized_request(
            method=SDWANHttpMethod.POST,
            path=path,
            json=payload.model_dump(mode="json"),
        )
        return ServiceResponse.model_validate(response["data"])  # type: ignore

    async def get_cpe_info(self, cpe_id: str) -> CPEInfoResponse:
        """Get CPE info"""

        response = await self.authorized_request(
            method=SDWANHttpMethod.GET,
            path=SDWANCspHttpClientEndpoints.CPE + f"/{cpe_id}",
        )
        return CPEInfoResponse.model_validate(response)

    async def get_device_objects(
        self, dev_obj_id: str | None = None
    ) -> list[DeviceObjectResponse]:
        """Get device objects list
        Return one device object (in list) if dev_obj_id is provided
        """
        path = SDWANCspHttpClientEndpoints.DEVICE_OBJECTS
        if dev_obj_id:
            path += f"?dev_obj_id={dev_obj_id}"  # type: ignore

        response = await self.authorized_request(
            method=SDWANHttpMethod.GET,
            path=path,
        )
        return [DeviceObjectResponse.model_validate(do) for do in response["result"]]  # type: ignore

    async def get_policies(
        self,
        dev_obj_id: str | None = None,
    ) -> list[PolicyResponse]:
        """Get policies list
        Returns device object and global policies (only together) if dev_obj_id is provided
        """
        path = SDWANCspHttpClientEndpoints.POLICIES

        if dev_obj_id:
            dev_obj_res: DeviceObjectResponse = (
                await self.get_device_objects(
                    dev_obj_id=dev_obj_id,
                )
            )[0]

            parent_dev_obj_ids: list[str] = (
                dev_obj_res.parent_dev_obj_ids
            )  # selected dev obj parents
            parent_dev_obj_ids.append(
                dev_obj_id
            )  # append selected dev obj as parent for policies

            # not use params because of encoding url string (problem is on sd-wan server api)
            # global and target together only
            path += f"?parents={',+'.join(parent_dev_obj_ids)}"  # type: ignore

        response = await self.authorized_request(
            method=SDWANHttpMethod.GET,
            path=path,
            params={"with_null_policy": False},
        )

        total: int = response["meta"]["total"]  # type: ignore
        if len(response["data"]) < total:  # type: ignore
            response = await self.authorized_request(
                method=SDWANHttpMethod.GET,
                path=path,
                params={"with_null_policy": False, "limit": total},
            )

        return [PolicyResponse.model_validate(p) for p in response["data"]]  # type: ignore

    async def get_policies_by_ids(
        self,
        ids: list[int],
    ) -> list[PolicyResponse]:
        """Get policies list by ids filtering"""
        _ids = set(ids)
        params = {
            "query": f"policy_id = ({' '.join(map(str, _ids))})",
            "with_null_policy": False,
        }

        response = await self.authorized_request(
            method=SDWANHttpMethod.GET,
            path=SDWANCspHttpClientEndpoints.POLICIES,
            params=params,
        )

        return [PolicyResponse.model_validate(p) for p in response["data"]]  # type: ignore

    async def create_policy(self, payload: CreatePolicyRequest) -> int:
        """Create policy"""

        response = await self.authorized_request(
            method=SDWANHttpMethod.POST,
            path=SDWANCspHttpClientEndpoints.POLICIES,
            json=payload.model_dump(mode="json"),
        )
        return response  # type: ignore
