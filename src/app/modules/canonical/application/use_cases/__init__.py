"""Stable canonical application use-case API surface."""

from app.modules.canonical.application.use_cases.get_canonical_issues import (
    GetCanonicalIssuesQuery,
    GetCanonicalIssuesResult,
    GetCanonicalIssuesUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_object import (
    GetCanonicalObjectQuery,
    GetCanonicalObjectResult,
    GetCanonicalObjectUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_objects import (
    GetCanonicalObjectsQuery,
    GetCanonicalObjectsResult,
    GetCanonicalObjectsUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_rule import (
    GetCanonicalRuleQuery,
    GetCanonicalRuleResult,
    GetCanonicalRuleUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_rule_scope import (
    GetCanonicalRuleScopeQuery,
    GetCanonicalRuleScopeResult,
    GetCanonicalRuleScopeUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_rules import (
    GetCanonicalRulesQuery,
    GetCanonicalRulesResult,
    GetCanonicalRulesUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_snapshot import (
    GetCanonicalSnapshotQuery,
    GetCanonicalSnapshotResult,
    GetCanonicalSnapshotUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_zone import (
    GetCanonicalZoneQuery,
    GetCanonicalZoneResult,
    GetCanonicalZoneUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_zones import (
    GetCanonicalZonesQuery,
    GetCanonicalZonesResult,
    GetCanonicalZonesUseCase,
)
from app.modules.canonical.application.use_cases.get_latest_snapshot_for_source import (
    GetLatestCanonicalSnapshotForSourceQuery,
    GetLatestCanonicalSnapshotForSourceResult,
    GetLatestCanonicalSnapshotForSourceUseCase,
)
from app.modules.canonical.application.use_cases.save_canonical_snapshot import (
    SaveCanonicalSnapshotCommand,
    SaveCanonicalSnapshotResult,
    SaveCanonicalSnapshotUseCase,
)

__all__ = [
    "GetCanonicalIssuesQuery",
    "GetCanonicalIssuesResult",
    "GetCanonicalIssuesUseCase",
    "GetCanonicalObjectQuery",
    "GetCanonicalObjectResult",
    "GetCanonicalObjectUseCase",
    "GetCanonicalObjectsQuery",
    "GetCanonicalObjectsResult",
    "GetCanonicalObjectsUseCase",
    "GetCanonicalRuleQuery",
    "GetCanonicalRuleResult",
    "GetCanonicalRuleScopeQuery",
    "GetCanonicalRuleScopeResult",
    "GetCanonicalRuleScopeUseCase",
    "GetCanonicalRuleUseCase",
    "GetCanonicalRulesQuery",
    "GetCanonicalRulesResult",
    "GetCanonicalRulesUseCase",
    "GetCanonicalSnapshotQuery",
    "GetCanonicalSnapshotResult",
    "GetCanonicalSnapshotUseCase",
    "GetCanonicalZoneQuery",
    "GetCanonicalZoneResult",
    "GetCanonicalZoneUseCase",
    "GetCanonicalZonesQuery",
    "GetCanonicalZonesResult",
    "GetCanonicalZonesUseCase",
    "GetLatestCanonicalSnapshotForSourceQuery",
    "GetLatestCanonicalSnapshotForSourceResult",
    "GetLatestCanonicalSnapshotForSourceUseCase",
    "SaveCanonicalSnapshotCommand",
    "SaveCanonicalSnapshotResult",
    "SaveCanonicalSnapshotUseCase",
]
