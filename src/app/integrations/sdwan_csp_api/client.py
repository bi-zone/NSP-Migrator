import asyncio
import logging
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
    CommitDataResponse,
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
    PoliciesResponse,
    PolicyResponse,
    ServiceCreateRequest,
    ServiceResponse,
    ServicesResponse,
    ZoneResponse,
    ZonesResponse,
)

logger = logging.getLogger(__name__)


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


YAQL_FILTERS_LIMIT = 50
SERVICES_MAX_LIMIT = 10_000
ADDR_OBJS_MAX_LIMIT = 10_000
POLICIES_MAX_LIMIT = 10_000


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
        vpc_id: str | None,
        requester: IAsyncHttpRequester,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._requester = requester
        self._vpc_id = vpc_id
        self._token: str | None = None
        self._auth_data: LoginResponse | None = None
        self._auth_lock = asyncio.Lock()

    # -- Internal Tools
    async def _get_auth_headers(self) -> dict[str, str]:
        """Return a dict with auth headers"""
        if self._token is None:
            async with self._auth_lock:
                if self._token is None:
                    await self.login()
        return {"Authorization": f"Bearer {self._token}"}

    async def login(self) -> LoginResponse:
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
                json=payload.model_dump(exclude_none=True),
            )
        except HttpResponseStatusError as exc:
            body = (exc.response_body or "").strip().replace("\n", " ")
            if len(body) > 300:
                body = f"{body[:300]}..."
            # for streamlit debugging
            detail = f" status={exc.status_code}"
            if body:
                detail = f"{detail} body={body!r}"
            raise SDWANCspHttpAuthError(f"Login to SD-WAN API failed:{detail}") from exc
        except (HttpRequestTransportError, HttpRequestTimeoutError) as exc:
            raise SDWANCspHttpConnectionError(
                "Network error while logging in to SD-WAN API"
            ) from exc

        try:
            serialized_response = LoginResponse.model_validate(response)
        except ValidationError as exc:
            raise SDWANCspHttpResponseError("Invalid login response schema") from exc

        self._auth_data = serialized_response
        self._token = serialized_response.token
        return serialized_response

    # -- Public methods
    @property
    def vpc_id(self) -> str:
        """Get vpc_id of sdwan client (if it selected)"""
        if self._vpc_id is None:
            raise SDWANCspHttpError("VPC is not selected")
        return self._vpc_id

    async def aclose(self) -> None:
        await self._requester.aclose()

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
    async def _request_make_commit(
        self, commit_name: str, commit_description: str, filter_expr: str | None = None
    ) -> int:
        """Request commit operation"""
        payload = CommitRuleObjectsRequest(
            name=commit_name,
            description=commit_description,
            filter=filter_expr,
        )

        response = await self.authorized_request(
            method=SDWANHttpMethod.POST,
            path=SDWANCspHttpClientEndpoints.COMMITS.format(vpc_id=self.vpc_id),
            json=payload.model_dump(mode="json", exclude_none=True),
        )

        if not isinstance(response, int):
            raise TypeError(
                f"Expected integer response from {SDWANCspHttpClientEndpoints.COMMITS}"
            )

        return response

    async def commit_full_state(
        self,
        commit_name: str,
        commit_description: str,
    ) -> int:
        """Commit a list of objects, that marked as created, linked and etc
        (full current state of changes on CSP). Returns commit object id.
        """
        return await self._request_make_commit(commit_name, commit_description)

    async def commit_entities(
        self,
        commit_name: str,
        commit_description: str,
        entities: list[CommitEntityDto],
    ) -> int:
        """Commit a list of filtered entities. Returns commit object id. UNUSED"""

        base_filter_template: str = (
            '(entity_kind = "{ent_kind}" and entity_id = {ent_id})'
        )
        filters_for_expr: list[str] = [
            base_filter_template.format(ent_kind=ent.kind, ent_id=ent.id)
            for ent in entities
        ]
        filter_expr: str = " or ".join(filters_for_expr)

        return await self._request_make_commit(
            commit_name, commit_description, filter_expr
        )

    async def get_commit_info(self, commit_id: int) -> CommitDataResponse:
        """Get commit info and linked diffs"""
        single_commit_info_response = await self.authorized_request(
            method=SDWANHttpMethod.GET,
            path=SDWANCspHttpClientEndpoints.COMMITS.format(vpc_id=self.vpc_id),
            params={"query": f"commit_id = {commit_id}"},
        )
        return CommitDataResponse.model_validate(single_commit_info_response["data"][0])  # type: ignore

    async def get_commit_diffs_info(self, commit_id: int) -> dict:
        """Get commit info and linked diffs"""
        diffs_info_response = await self.authorized_request(
            method=SDWANHttpMethod.GET,
            path=SDWANCspHttpClientEndpoints.DIFF.format(vpc_id=self.vpc_id),
            params={"for_commit": commit_id},
        )
        return diffs_info_response["data"]  # type: ignore

    async def apply_commit(self, commit_id: int) -> ApplyCommitResultResponse:
        """Apply the commit (sync configs with CPEs)"""
        # TODO: search info about "rollback" for apply process with API
        response = await self.authorized_request(
            method=SDWANHttpMethod.POST,
            path=SDWANCspHttpClientEndpoints.TASKS.format(vpc_id=self.vpc_id),
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

    # -- retrieve zones
    async def _fetch_all_zones(self) -> list[ZoneResponse]:
        """Fetch all zones"""
        response = await self.authorized_request(
            method=SDWANHttpMethod.GET,
            path=SDWANCspHttpClientEndpoints.ZONES,
        )
        result = ZonesResponse.model_validate(response)

        if result.total > len(result.result):
            response = await self.authorized_request(
                method=SDWANHttpMethod.GET,
                path=SDWANCspHttpClientEndpoints.ZONES,
                params={"limit": result.total},
            )
            result = ZonesResponse.model_validate(response)

        return result.result

    async def get_zones(
        self,
        ids: list[int] | None = None,
    ) -> list[ZoneResponse]:
        """Get zones"""
        # -- fetch all
        all_zones: list[ZoneResponse] = await self._fetch_all_zones()

        if not ids:
            return all_zones

        # -- filter by id
        ids_set = set(ids)  # deduplicate
        return list(filter(lambda z: z.id in ids_set, all_zones))

    # -- retrieve services
    async def _fetch_services_page(
        self,
        *,
        cursor: str | None = None,
    ) -> ServicesResponse:
        """Fetch a single services page."""
        params: dict[str, Any] = {
            "limit": SERVICES_MAX_LIMIT,
        }

        if cursor is not None:
            params["cursor"] = cursor

        path = SDWANCspHttpClientEndpoints.SERVICES.format(
            vpc_id=self.vpc_id,
        )

        response = await self.authorized_request(
            method=SDWANHttpMethod.GET,
            path=path,
            params=params,
        )

        try:
            return ServicesResponse.model_validate(response)
        except ValidationError as exc:
            raise SDWANCspHttpResponseError(
                f"Invalid services response schema: {exc}"
            ) from exc

    async def _fetch_all_services(
        self,
    ) -> list[ServiceResponse]:
        """Fetch all services by sequentially following pagination cursors."""
        services: list[ServiceResponse] = []
        _cursor: str | None = None
        _expected_total: int | None = None
        _seen_cursors: set[str] = set()

        while True:
            response: ServicesResponse = await self._fetch_services_page(
                cursor=_cursor,
            )
            if _expected_total is None:
                _expected_total = response.meta.total
            elif response.meta.total != _expected_total:
                raise SDWANCspHttpResponseError(
                    "Services total changed during pagination: "
                    f"expected {_expected_total}, got {response.meta.total}"
                )

            services.extend(response.data)

            next_cursor: str | None = response.meta.next_page
            if next_cursor is None:
                break

            if next_cursor in _seen_cursors:
                raise SDWANCspHttpResponseError(
                    "Services pagination returned a repeated cursor"
                )

            _seen_cursors.add(next_cursor)
            _cursor = next_cursor

        if _expected_total is not None and len(services) != _expected_total:
            raise SDWANCspHttpResponseError(
                "Incomplete services response: "
                f"expected {_expected_total}, got {len(services)}"
            )

        return services

    async def get_services(
        self,
        ids: list[int] | None = None,
    ) -> list[ServiceResponse]:
        """Get services with optional filtering."""
        all_services: list[ServiceResponse] = await self._fetch_all_services()

        if not ids:
            return all_services

        ids_set = set(ids)
        return list(filter(lambda s: s.id in ids_set, all_services))

    # -- retrieve address objects
    async def _fetch_addr_objects_page(
        self,
        *,
        query: str | None = None,
        cursor: str | None = None,
    ) -> AddrObjectsResponse:
        """Fetch a single address objects page."""
        params: dict[str, Any] = {
            "limit": ADDR_OBJS_MAX_LIMIT,
        }

        if cursor is not None:
            params["cursor"] = cursor
        if query is not None:
            params["query"] = query

        response = await self.authorized_request(
            method=SDWANHttpMethod.GET,
            path=SDWANCspHttpClientEndpoints.ADDR_OBJECTS,
            params=params,
        )

        try:
            return AddrObjectsResponse.model_validate(response)
        except ValidationError as exc:
            raise SDWANCspHttpResponseError(
                f"Invalid addr_objects response schema: {exc}"
            ) from exc

    async def _fetch_all_addr_objects(
        self,
        *,
        query: str | None = None,
    ) -> list[AddrObjectResponse]:
        """Fetch all address objects matching the provided query."""
        addr_objects: list[AddrObjectResponse] = []
        _cursor: str | None = None
        _expected_total: int | None = None
        _seen_cursors: set[str] = set()

        while True:
            response: AddrObjectsResponse = await self._fetch_addr_objects_page(
                query=query,
                cursor=_cursor,
            )

            if _expected_total is None:
                _expected_total = response.meta.total
            elif response.meta.total != _expected_total:
                raise SDWANCspHttpResponseError(
                    "Address objects total changed during pagination: "
                    f"expected {_expected_total}, got {response.meta.total}"
                )

            addr_objects.extend(response.data)

            next_cursor: str | None = response.meta.next_page
            if next_cursor is None:
                break

            if next_cursor in _seen_cursors:
                raise SDWANCspHttpResponseError(
                    "Address objects pagination returned a repeated cursor"
                )

            _seen_cursors.add(next_cursor)
            _cursor = next_cursor

        if _expected_total is not None and len(addr_objects) != _expected_total:
            raise SDWANCspHttpResponseError(
                "Incomplete address objects response: "
                f"expected {_expected_total}, got {len(addr_objects)}"
            )

        return addr_objects

    async def get_addr_objects(
        self,
        ids: list[int] | None = None,
        parents_ids: list[int] | None = None,
    ) -> list[AddrObjectResponse]:
        """
        Get address objects with optional ID and parent ID filtering.

        Parent ID filtering is performed by the SD-WAN API using YAQL queries.
        Object ID filtering is applied locally after all matching objects have
        been fetched.

        Large parent ID filters are split into YAQL-sized chunks. Results from
        different chunks are merged while preserving distinct object-parent
        combinations.
        """
        if parents_ids:
            deduplicated_parents_ids = list(dict.fromkeys(parents_ids))

            parents_ids_chunks: list[list[int]] = [
                deduplicated_parents_ids[i : i + YAQL_FILTERS_LIMIT]
                for i in range(0, len(deduplicated_parents_ids), YAQL_FILTERS_LIMIT)
            ]

            chunks_results: list[list[AddrObjectResponse]] = await asyncio.gather(
                *(
                    self._fetch_all_addr_objects(
                        query=" or ".join(
                            f"parents = ({parent_id})"
                            for parent_id in parents_ids_chunk
                        )
                    )
                    for parents_ids_chunk in parents_ids_chunks
                )
            )

            addr_objects_res: list[AddrObjectResponse] = [
                addr_object
                for chunk_result in chunks_results
                for addr_object in chunk_result
            ]

            # Deduplicate - the same object may match parent IDs from different YAQL chunks.
            deduplicated_addr_objects = {
                addr_object.id: addr_object for addr_object in addr_objects_res
            }
            addr_objects = list(deduplicated_addr_objects.values())

        else:
            addr_objects: list[AddrObjectResponse] = (  # type: ignore
                await self._fetch_all_addr_objects()
            )

        if ids:
            ids_set = set(ids)
            addr_objects = [
                addr_object for addr_object in addr_objects if addr_object.id in ids_set
            ]

        return addr_objects

    # -- retrieve networks
    async def _fetch_all_networks(self) -> list[NetworkResponse]:
        """Fetch all networks"""
        response = await self.authorized_request(
            method=SDWANHttpMethod.GET,
            path=SDWANCspHttpClientEndpoints.NETWORKS,
        )
        result = NetworksResponse.model_validate(response)

        if result.total > len(result.result):
            response = await self.authorized_request(
                method=SDWANHttpMethod.GET,
                path=SDWANCspHttpClientEndpoints.NETWORKS,
                params={"limit": result.total},
            )
            result = NetworksResponse.model_validate(response)

        return result.result

    async def get_networks(
        self,
        network_ids: list[int] | None = None,
    ) -> list[NetworkResponse]:
        """Get networks"""
        # -- fetch all
        all_networks: list[NetworkResponse] = await self._fetch_all_networks()

        if not network_ids:
            return all_networks

        # -- filter by id
        network_ids_set = set(network_ids)  # deduplicate
        return list(filter(lambda n: n.network_id in network_ids_set, all_networks))

    # -- create operations
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
        path = SDWANCspHttpClientEndpoints.SERVICES_V1.format(vpc_id=self.vpc_id)

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

    # -- retrieve policies
    async def _fetch_policies_page(
        self,
        *,
        parents: list[str] | None = None,
        query: str | None = None,
        cursor: str | None = None,
    ) -> PoliciesResponse:
        """Fetch a single policies page."""
        params: dict[str, bool | str | int] = {
            "with_null_policy": False,
            "limit": POLICIES_MAX_LIMIT,
        }

        if cursor is not None:
            params["cursor"] = cursor
        if parents:
            params["parents"] = ", ".join(parents)
        if query is not None:
            params["query"] = query

        response = await self.authorized_request(
            method=SDWANHttpMethod.GET,
            path=SDWANCspHttpClientEndpoints.POLICIES,
            params=params,
        )

        try:
            return PoliciesResponse.model_validate(response)
        except ValidationError as exc:
            raise SDWANCspHttpResponseError(
                f"Invalid policies response schema: {exc}"
            ) from exc

    async def _fetch_all_policies(
        self,
        *,
        parents: list[str] | None = None,
        query: str | None = None,
    ) -> list[PolicyResponse]:
        """Fetch all policies by sequentially following pagination cursors."""
        policies: list[PolicyResponse] = []

        _cursor: str | None = None
        _expected_total: int | None = None
        _seen_cursors: set[str] = set()

        while True:
            response: PoliciesResponse = await self._fetch_policies_page(
                parents=parents,
                query=query,
                cursor=_cursor,
            )

            if _expected_total is None:
                _expected_total = response.meta.total
            elif response.meta.total != _expected_total:
                raise SDWANCspHttpResponseError(
                    "Policies total changed during pagination: "
                    f"expected {_expected_total}, got {response.meta.total}"
                )

            policies.extend(response.data)

            next_cursor: str | None = response.meta.next_page
            if next_cursor is None:
                break

            if next_cursor in _seen_cursors:
                raise SDWANCspHttpResponseError(
                    "Policies pagination returned a repeated cursor"
                )

            _seen_cursors.add(next_cursor)
            _cursor = next_cursor

        if _expected_total is not None and len(policies) != _expected_total:
            raise SDWANCspHttpResponseError(
                "Incomplete policies response: "
                f"expected {_expected_total}, got {len(policies)}"
            )

        return policies

    async def get_policies(
        self,
        dev_obj_id: str | None = None,
    ) -> list[PolicyResponse]:
        """
        Get all policies.

        If `dev_obj_id` is provided, return policies assigned to the selected
        device object and its parent device objects (cascade).
        """
        parent_dev_obj_ids: list[str] | None = None

        if dev_obj_id is not None:
            device_objects: list[DeviceObjectResponse] = (  # fmt: no
                await self.get_device_objects(
                    dev_obj_id=dev_obj_id,
                )
            )

            if not device_objects:
                raise SDWANCspHttpError(f"Device object {dev_obj_id!r} was not found")

            dev_obj = device_objects[0]

            parent_dev_obj_ids = [
                *dev_obj.parent_dev_obj_ids,
                dev_obj_id,
            ]

        return await self._fetch_all_policies(
            parents=parent_dev_obj_ids,
        )

    async def _fetch_policies_by_ids_chunk(
        self,
        ids: list[int],
    ) -> list[PolicyResponse]:
        """Fetch all policies matching a single YAQL IDs chunk."""
        query = f"policy_id = ({' '.join(map(str, ids))})"

        return await self._fetch_all_policies(
            query=query,
        )

    async def get_policies_by_ids(
        self,
        ids: list[int],
    ) -> list[PolicyResponse]:
        """
        Get policies by IDs using server-side YAQL filtering.

        IDs are deduplicated and split into chunks of the maximum allowed
        YAQL filter size. Each chunk is fully fetched using cursor pagination,
        and all results are merged into a single list.
        """
        if not ids:
            return []

        deduplicated_ids: list[int] = list(set(ids))

        ids_chunks: list[list[int]] = [
            deduplicated_ids[i : i + YAQL_FILTERS_LIMIT]
            for i in range(0, len(deduplicated_ids), YAQL_FILTERS_LIMIT)
        ]

        chunks_results: list[list[PolicyResponse]] = await asyncio.gather(
            *(self._fetch_policies_by_ids_chunk(ids_chunk) for ids_chunk in ids_chunks)
        )

        return [policy for chunk_result in chunks_results for policy in chunk_result]

    async def create_policy(self, payload: CreatePolicyRequest) -> int:
        """Create policy"""

        response = await self.authorized_request(
            method=SDWANHttpMethod.POST,
            path=SDWANCspHttpClientEndpoints.POLICIES,
            json=payload.model_dump(mode="json"),
        )
        return response  # type: ignore
