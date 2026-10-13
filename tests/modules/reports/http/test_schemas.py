from types import SimpleNamespace
from uuid import uuid4

from app.modules.reports.domain.enums import (
    ReportRuleAction,
    ReportRuleMigrationResult,
)
from app.modules.reports.http.schemas import (
    CSPProfileHeaderResponse,
    ReportRuleResponse,
)


def test_csp_profile_header_response_includes_base_url() -> None:
    response = CSPProfileHeaderResponse.model_validate(
        SimpleNamespace(
            id=uuid4(),
            name="Production",
            base_url="https://sdwan.example.test",
        )
    )

    assert response.base_url == "https://sdwan.example.test"


def test_report_rule_response_includes_priority() -> None:
    response = ReportRuleResponse.model_validate(
        SimpleNamespace(
            policy_name="allow-web",
            action=ReportRuleAction.ACCEPT,
            priority=10,
            src_zone_names=("LAN",),
            dst_zone_names=("WAN",),
            src_addr_values=("10.10.0.0/24",),
            dst_addr_values=("203.0.113.10",),
            service_values=("tcp/443",),
            migration_result=ReportRuleMigrationResult.PUSHED,
            reason="Success",
        )
    )

    assert response.priority == 10
