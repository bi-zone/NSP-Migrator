from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.execute.di.dependencies import (
    get_execute_plan_rules_use_case,
    get_prepare_execute_plan_use_case,
    get_push_execute_plan_rules_use_case,
)
from app.modules.execute.application.dto import CommitInfoDTO, PushRuleResultDTO
from app.modules.execute.application.use_cases.push_execute_plan_rules import (
    PushExecutePlanRulesResult,
)
from app.modules.execute.domain.entities import ExecutePlan, ExecutePlanRule
from app.modules.execute.domain.enums import RuleMatchStatus, SdwanRuleAction
from app.modules.execute.domain.value_objects import PlannedRuleDraft
from app.modules.execute.http.router import execute_router


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
    app.include_router(execute_router)
    return TestClient(app)


def _plan_rule(plan_id: UUID) -> ExecutePlanRule:
    return ExecutePlanRule.create(
        execute_plan_id=plan_id,
        mapping_scope_rule_id=uuid4(),
        priority=0,
        draft=PlannedRuleDraft(
            name="allow-web",
            action=SdwanRuleAction.ACCEPT,
            src_zones=[1],
            dst_zones=[2],
            src_addr_objects=[10],
            dst_addr_objects=[20],
            services=[30],
        ),
        matched_sdwan_rule_id=None,
        match_status=RuleMatchStatus.NEW,
        match_info="Clearly new rule for migration",
    )


def test_get_plan_rules_route_forwards_match_status_and_serializes_draft() -> None:
    plan = ExecutePlan.create(mapping_scope_id=uuid4(), catalog_fingerprint="catalog")
    plan_rule = _plan_rule(plan.id)
    use_case = _ResultUseCase(SimpleNamespace(plan_rules=[plan_rule]))
    client = _client()
    client.app.dependency_overrides[get_execute_plan_rules_use_case] = lambda: use_case

    response = client.get(
        f"/execute/plans/{plan.id}/rules",
        params={"match_status": "NEW"},
    )

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(plan_rule.id)
    assert response.json()[0]["match_status"] == "NEW"
    assert response.json()[0]["priority"] == 0
    assert response.json()[0]["push_status"] == "PENDING"
    assert response.json()[0]["draft"]["name"] == "allow-web"
    assert use_case.command is not None
    assert use_case.command.execute_plan_id == plan.id  # type: ignore[union-attr]
    assert use_case.command.match_status == RuleMatchStatus.NEW  # type: ignore[union-attr]


def test_prepare_plan_route_forwards_mapping_scope_and_returns_summary() -> None:
    plan_id = uuid4()
    mapping_scope_id = uuid4()
    use_case = _ResultUseCase(
        SimpleNamespace(
            id=plan_id,
            mapping_scope_id=mapping_scope_id,
            sdwan_target_id="target-1",
            created_at="2026-01-01T00:00:00Z",
            total_rules=3,
            new_rules=1,
            matched_rules=1,
            covered_rules=1,
            errors_through_match=0,
            excluded_existing_rules=[],
        )
    )
    client = _client()
    client.app.dependency_overrides[get_prepare_execute_plan_use_case] = lambda: (
        use_case
    )

    response = client.post(
        "/execute/plans", params={"mapping_scope_id": mapping_scope_id}
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(plan_id)
    assert response.json()["total_rules"] == 3
    assert use_case.command is not None
    assert use_case.command.mapping_scope_id == mapping_scope_id  # type: ignore[union-attr]


def test_push_rules_route_returns_success_and_failure_outcomes() -> None:
    plan_id = uuid4()
    succeeded_rule_id = uuid4()
    failed_rule_id = uuid4()
    use_case = _ResultUseCase(
        PushExecutePlanRulesResult(
            rules=[],
            push_results=[
                PushRuleResultDTO(
                    execute_plan_rule_id=succeeded_rule_id,
                    rule_name="allow-web",
                    sdwan_rule_id=901,
                    error=None,
                ),
                PushRuleResultDTO(
                    execute_plan_rule_id=failed_rule_id,
                    rule_name="deny-admin",
                    sdwan_rule_id=None,
                    error="SD-WAN rejected policy",
                ),
            ],
            commit_info=CommitInfoDTO(
                commit_id=1,
                name="test-commit",
                description="",
            ),
        )
    )
    client = _client()
    client.app.dependency_overrides[get_push_execute_plan_rules_use_case] = lambda: (
        use_case
    )

    response = client.post(f"/execute/plans/{plan_id}/push-rules")

    assert response.status_code == 200
    assert response.json() == {
        "rules": [],
        "push_results": [
            {
                "execute_plan_rule_id": str(succeeded_rule_id),
                "rule_name": "allow-web",
                "sdwan_rule_id": 901,
                "error": None,
            },
            {
                "execute_plan_rule_id": str(failed_rule_id),
                "rule_name": "deny-admin",
                "sdwan_rule_id": None,
                "error": "SD-WAN rejected policy",
            },
        ],
    }
