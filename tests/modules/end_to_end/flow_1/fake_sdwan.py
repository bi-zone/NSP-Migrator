"""Stateful SD-WAN client fake used only by the flow_1 acceptance scenario."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from app.integrations.sdwan_csp_api.schemas import (
    AddrObject,
    AddrObjectResponse,
    CommitDataResponse,
    CreatePolicyRequest,
    DeviceObjectResponse,
    LoginResponse,
    PolicyResponse,
    ServiceResponse,
    ZoneResponse,
)


def _address_object(
    *, object_id: int, name: str, data: dict[str, object]
) -> AddrObjectResponse:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return AddrObjectResponse.model_validate(
        {
            "id": object_id,
            "parents": [],
            "name": name,
            "description": "flow_1 test object",
            "created_at": now,
            "updated_at": now,
            "data": data,
        }
    )


def _policy(
    *,
    policy_id: int,
    name: str,
    src_address_ids: list[int],
    dst_address_ids: list[int],
    service_ids: list[int],
) -> PolicyResponse:
    return PolicyResponse.model_validate(
        {
            "type": "policy",
            "policy_id": policy_id,
            "parents": ["device-flow-1"],
            "order": str(policy_id),
            "priority": "local",
            "name": name,
            "description": "flow_1 test policy",
            "tags": ["flow_1"],
            "activated": True,
            "action": "ACCEPT",
            "log": False,
            "l4_inspection": False,
            "ambiguous": False,
            "ambiguous_reason": None,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "snat": None,
            "dnat": None,
            "ingress_zone": [1],
            "egress_zone": [2],
            "src_address": [
                AddrObject(type="host", id=object_id) for object_id in src_address_ids
            ],
            "dst_address": [
                AddrObject(type="host", id=object_id) for object_id in dst_address_ids
            ],
            "service": service_ids,
            "src_idents": [],
            "dst_idents": [],
        }
    )


@dataclass(slots=True)
class FakeSDWANState:
    """Fixed catalog plus mutable policies created by the workflow."""

    zones: list[ZoneResponse] = field(
        default_factory=lambda: [
            ZoneResponse(
                id=1,
                zone_id=1,
                name="outside",
                typ="wan",
                vrf_id=None,
                is_permanent=True,
                is_default=False,
                description="flow_1 outside zone",
            ),
            ZoneResponse(
                id=2,
                zone_id=2,
                name="inside",
                typ="lan",
                vrf_id=None,
                is_permanent=True,
                is_default=False,
                description="flow_1 inside zone",
            ),
        ]
    )
    address_objects: list[AddrObjectResponse] = field(
        default_factory=lambda: [
            _address_object(
                object_id=100,
                name="src-app",
                data={"type": "host", "host": "10.0.0.1", "raw": False},
            ),
            _address_object(
                object_id=101,
                name="dst-exact-primary",
                data={"type": "host", "host": "10.0.0.2", "raw": False},
            ),
            _address_object(
                object_id=102,
                name="dst-exact-secondary",
                data={"type": "host", "host": "10.0.0.2", "raw": False},
            ),
            _address_object(
                object_id=104,
                name="manual-covered-destination",
                data={"type": "host", "host": "10.0.0.30", "raw": False},
            ),
            _address_object(
                object_id=105,
                name="dst-new",
                data={"type": "host", "host": "10.0.0.4", "raw": False},
            ),
            _address_object(
                object_id=200,
                name="covered-network",
                data={"type": "prefix", "prefix": "10.0.0.0/24", "raw": False},
            ),
        ]
    )
    services: list[ServiceResponse] = field(
        default_factory=lambda: [
            ServiceResponse(
                id=10, name="https", l4_proto="tcp", ranges=[{"start": 443, "end": 443}]
            ),
            ServiceResponse(
                id=11, name="http", l4_proto="tcp", ranges=[{"start": 80, "end": 80}]
            ),
            ServiceResponse(
                id=12, name="ssh", l4_proto="tcp", ranges=[{"start": 22, "end": 22}]
            ),
        ]
    )
    policies: list[PolicyResponse] = field(
        default_factory=lambda: [
            _policy(
                policy_id=501,
                name="already-exact",
                src_address_ids=[100],
                dst_address_ids=[101],
                service_ids=[10],
            ),
            _policy(
                policy_id=502,
                name="already-covers",
                src_address_ids=[100],
                dst_address_ids=[200],
                service_ids=[11],
            ),
        ]
    )
    created_policy_requests: list[CreatePolicyRequest] = field(default_factory=list)
    client_connections: list[tuple[UUID, str | None]] = field(default_factory=list)
    closed_clients: int = 0
    commits: list[tuple[str, str]] = field(default_factory=list)

    @property
    def device_object(self) -> DeviceObjectResponse:
        return DeviceObjectResponse.model_validate(
            {
                "id": 1,
                "dev_obj_id": "device-flow-1",
                "parent_dev_obj_ids": [],
                "vpc_id": "vpc-flow-1",
                "type": "device",
                "name": "Flow 1 device",
                "description": "deterministic test target",
                "depth": 0,
                "created_at": 0,
                "updated_at": 0,
                "is_global": False,
                "cpe": {
                    "id": 1,
                    "cpe_id": "cpe-flow-1",
                    "cconf_id": "cconf-flow-1",
                    "vpc_id": "vpc-flow-1",
                    "sid": None,
                    "name": "Flow 1 CPE",
                    "description": "deterministic test target",
                },
                "cconf": None,
                "cpe_cluster": [],
            }
        )


class FakeSDWANClient:
    """Subset of the SD-WAN HTTP-client protocol exercised by flow_1."""

    def __init__(self, state: FakeSDWANState, vpc_id: str | None) -> None:
        self._state = state
        self.vpc_id = vpc_id

    async def login(self) -> LoginResponse:
        return LoginResponse.model_validate(
            {
                "token": "flow-1-token",
                "vpc_id": self.vpc_id,
                "allowed_vpcs": [
                    {
                        "vpc_id": "vpc-flow-1",
                        "customer_name": "Flow 1 customer",
                        "project_name": "Flow 1 project",
                        "cuid": "flow-1-cuid",
                        "pid": "flow-1-pid",
                    }
                ],
            }
        )

    async def aclose(self) -> None:
        self._state.closed_clients += 1

    async def health_check(self) -> None:
        return None

    async def get_zones(self, ids: list[int] | None = None) -> list[ZoneResponse]:
        if not ids:
            return list(self._state.zones)
        return [zone for zone in self._state.zones if zone.id in ids]

    async def get_services(self, ids: list[int] | None = None) -> list[ServiceResponse]:
        if not ids:
            return list(self._state.services)
        return [service for service in self._state.services if service.id in ids]

    async def get_addr_objects(
        self,
        ids: list[int] | None = None,
        parents_ids: list[int] | None = None
    ) -> list[AddrObjectResponse]:
        if ids:
            return [
                item for item in self._state.address_objects if item.id in ids
            ]

        if parents_ids:
            return []

        return self._state.address_objects

    async def get_networks(self, *, network_ids=None, limit=None):
        return []

    async def get_device_objects(
        self, *, dev_obj_id=None
    ) -> list[DeviceObjectResponse]:
        device = self._state.device_object
        return [device] if dev_obj_id in (None, device.dev_obj_id) else []

    async def get_policies(self, *, dev_obj_id=None) -> list[PolicyResponse]:
        return list(self._state.policies) if dev_obj_id == "device-flow-1" else []

    async def create_policy(self, payload: CreatePolicyRequest) -> int:
        policy_id = 900 + len(self._state.created_policy_requests)
        self._state.created_policy_requests.append(payload)
        self._state.policies.append(
            _policy(
                policy_id=policy_id,
                name=payload.name,
                src_address_ids=payload.src_address,
                dst_address_ids=payload.dst_address,
                service_ids=payload.service,
            )
        )
        return policy_id

    async def get_policies_by_ids(self, *, ids: list[int]) -> list[PolicyResponse]:
        return [policy for policy in self._state.policies if policy.policy_id in ids]

    async def commit_full_state(
        self, commit_name: str, commit_description: str
    ) -> int:
        self._state.commits.append((commit_name, commit_description))
        return len(self._state.commits)

    async def get_commit_info(self, commit_id: int) -> CommitDataResponse:
        commit_name, commit_description = self._state.commits[commit_id - 1]
        return CommitDataResponse(
            commit_id=commit_id,
            name=commit_name,
            description=commit_description,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            user_id="flow-1-operator",
            is_applied=False,
            applied_by_task_id=None,
            applied_cpe_ids=None,
            synchronized_cpe_ids=None,
        )


@dataclass(slots=True)
class FakeSDWANClientFactory:
    """Factory seam used by the real profile connection tester and provider."""

    state: FakeSDWANState

    def create(self, *, profile, credentials, vpc_id: str | None) -> FakeSDWANClient:
        del credentials
        self.state.client_connections.append((profile.id, vpc_id))
        return FakeSDWANClient(self.state, vpc_id)
