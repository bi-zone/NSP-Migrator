from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.integrations.sdwan_csp_api.gateways.enums import SdwanDeviceObjectType
from app.integrations.sdwan_csp_api.gateways.models import SdwanDeviceObject
from app.modules.mapping.di.dependencies import (
    get_map_canonical_to_sdwan_use_case,
    get_sdwan_targets_use_case_dep,
)
from app.modules.mapping.domain.enums import MappingScopeRulesPriority
from app.modules.mapping.http.router import mapping_router


class _ResultUseCase:
    def __init__(self, result: object) -> None:
        self.result = result
        self.command: object | None = None

    async def execute(
        self,
        value: object | None = None,
        *,
        command: object | None = None,
        query: object | None = None,
    ) -> object:
        self.command = command or query or value
        return self.result


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(mapping_router)
    return TestClient(app)


def test_map_canonical_route_converts_query_values_to_command_and_response() -> None:
    scope_id = uuid4()
    use_case = _ResultUseCase(
        SimpleNamespace(
            mapping_scope_id=scope_id,
            mapping_results_summary=SimpleNamespace(
                total_entities=2,
                matched_entities=1,
                ambiguous=0,
                unresolved=1,
                zones_total=0,
                zones_matched=0,
                addr_total=1,
                addr_matched=1,
                services_total=1,
                services_matched=0,
            ),
            mapped_rules_count=3,
        )
    )
    client = _client()
    client.app.dependency_overrides[get_map_canonical_to_sdwan_use_case] = lambda: (
        use_case
    )
    profile_id = uuid4()
    snapshot_id = uuid4()
    canonical_rule_ids = [uuid4(), uuid4()]

    response = client.post(
        "/mapping/map-canonical-to-sdwan",
        params=[
            ("mapping_scope_title", "migration-1"),
            ("csp_profile_id", str(profile_id)),
            ("vpc_id", "vpc-1"),
            ("sdwan_target_id", "target-1"),
            ("rules_priority", "post"),
            ("canonical_snapshot_id", str(snapshot_id)),
            *(("canonical_rules_ids", str(rule_id)) for rule_id in canonical_rule_ids),
        ],
    )

    assert response.status_code == 200
    assert response.json()["mapping_scope_id"] == str(scope_id)
    assert response.json()["mapping_results_summary"]["unresolved"] == 1
    assert response.json()["mapped_rules_count"] == 3
    assert use_case.command is not None
    assert use_case.command.mapping_scope_title == "migration-1"  # type: ignore[union-attr]
    assert use_case.command.csp_profile_id == profile_id  # type: ignore[union-attr]
    assert use_case.command.canonical_snapshot_id == snapshot_id  # type: ignore[union-attr]
    assert use_case.command.canonical_rules_ids == canonical_rule_ids  # type: ignore[union-attr]
    assert use_case.command.rules_priority == MappingScopeRulesPriority.POST  # type: ignore[union-attr]


def test_sdwan_targets_route_uses_injected_use_case_and_serializes_target() -> None:
    target = SdwanDeviceObject(
        dev_obj_id="target-1",
        name="Branch firewall",
        type=SdwanDeviceObjectType.DEVICE,
        cpe_id="cpe-1",
    )
    use_case = _ResultUseCase(SimpleNamespace(targets=[target]))
    client = _client()
    client.app.dependency_overrides[get_sdwan_targets_use_case_dep] = lambda: use_case
    profile_id = uuid4()

    response = client.get(
        "/mapping/sdwan_targets",
        params={"csp_profile_id": str(profile_id), "vpc_id": "vpc-1"},
    )

    assert response.status_code == 200
    assert response.json() == [
        {"dev_obj_id": "target-1", "name": "Branch firewall", "cpe_id": "cpe-1"}
    ]
    assert use_case.command is not None
    assert use_case.command.csp_profile_id == profile_id  # type: ignore[union-attr]
    assert use_case.command.vpc_id == "vpc-1"  # type: ignore[union-attr]
