from fastapi import Depends, Request

from app.di.dependencies import get_di_container
from app.modules.canonical.application.use_cases.get_canonical_issues import (
    GetCanonicalIssuesUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_object import (
    GetCanonicalObjectUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_objects import (
    GetCanonicalObjectsUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_rule import (
    GetCanonicalRuleUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_rule_scope import (
    GetCanonicalRuleScopeUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_rules import (
    GetCanonicalRulesUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_snapshot import (
    GetCanonicalSnapshotUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_zone import (
    GetCanonicalZoneUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_zones import (
    GetCanonicalZonesUseCase,
)
from app.modules.canonical.application.use_cases.save_canonical_snapshot import (
    SaveCanonicalSnapshotUseCase,
)
from app.modules.canonical.di.container import CanonicalModuleContainer


def get_canonical_module_container(request: Request) -> CanonicalModuleContainer:
    return get_di_container(request).canonical_module()


def get_canonical_snapshot_use_case(
    container: CanonicalModuleContainer = Depends(get_canonical_module_container),
) -> GetCanonicalSnapshotUseCase:
    return container.get_canonical_snapshot_use_case()


def get_canonical_zones_use_case(
    container: CanonicalModuleContainer = Depends(get_canonical_module_container),
) -> GetCanonicalZonesUseCase:
    return container.get_canonical_zones_use_case()


def get_canonical_objects_use_case(
    container: CanonicalModuleContainer = Depends(get_canonical_module_container),
) -> GetCanonicalObjectsUseCase:
    return container.get_canonical_objects_use_case()


def get_canonical_rules_use_case(
    container: CanonicalModuleContainer = Depends(get_canonical_module_container),
) -> GetCanonicalRulesUseCase:
    return container.get_canonical_rules_use_case()


def get_canonical_issues_use_case(
    container: CanonicalModuleContainer = Depends(get_canonical_module_container),
) -> GetCanonicalIssuesUseCase:
    return container.get_canonical_issues_use_case()


def save_canonical_snapshot_use_case(
    container: CanonicalModuleContainer = Depends(get_canonical_module_container),
) -> SaveCanonicalSnapshotUseCase:
    return container.save_canonical_snapshot_use_case()


def get_canonical_zone_use_case(
    container: CanonicalModuleContainer = Depends(get_canonical_module_container),
) -> GetCanonicalZoneUseCase:
    return container.get_canonical_zone_use_case()


def get_canonical_object_use_case(
    container: CanonicalModuleContainer = Depends(get_canonical_module_container),
) -> GetCanonicalObjectUseCase:
    return container.get_canonical_object_use_case()


def get_canonical_rule_use_case(
    container: CanonicalModuleContainer = Depends(get_canonical_module_container),
) -> GetCanonicalRuleUseCase:
    return container.get_canonical_rule_use_case()


def get_canonical_rule_scope_use_case(
    container: CanonicalModuleContainer = Depends(get_canonical_module_container),
) -> GetCanonicalRuleScopeUseCase:
    return container.get_canonical_rule_scope_use_case()
