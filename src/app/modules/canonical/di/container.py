from dependency_injector import providers
from dependency_injector.containers import DeclarativeContainer

from app.modules.canonical.adapters.db.uow import CanonicalUoW
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
from app.modules.canonical.application.use_cases.get_latest_snapshot_for_source import (
    GetLatestCanonicalSnapshotForSourceUseCase,
)
from app.modules.canonical.application.use_cases.save_canonical_snapshot import (
    SaveCanonicalSnapshotUseCase,
)


class CanonicalModuleContainer(DeclarativeContainer):
    session_factory: providers.Dependency = providers.Dependency()

    uow = providers.Factory(CanonicalUoW, session_factory=session_factory)

    save_canonical_snapshot_use_case = providers.Factory(
        SaveCanonicalSnapshotUseCase, uow=uow
    )
    get_canonical_snapshot_use_case = providers.Factory(
        GetCanonicalSnapshotUseCase, uow=uow
    )
    get_latest_snapshot_for_source_use_case = providers.Factory(
        GetLatestCanonicalSnapshotForSourceUseCase, uow=uow
    )
    get_canonical_zones_use_case = providers.Factory(GetCanonicalZonesUseCase, uow=uow)
    get_canonical_objects_use_case = providers.Factory(
        GetCanonicalObjectsUseCase, uow=uow
    )
    get_canonical_rules_use_case = providers.Factory(GetCanonicalRulesUseCase, uow=uow)
    get_canonical_issues_use_case = providers.Factory(
        GetCanonicalIssuesUseCase, uow=uow
    )

    get_canonical_zone_use_case = providers.Factory(GetCanonicalZoneUseCase, uow=uow)
    get_canonical_object_use_case = providers.Factory(
        GetCanonicalObjectUseCase, uow=uow
    )
    get_canonical_rule_use_case = providers.Factory(GetCanonicalRuleUseCase, uow=uow)
    get_canonical_rule_scope_use_case = providers.Factory(
        GetCanonicalRuleScopeUseCase, uow=uow
    )
