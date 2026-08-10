from app.infrastructure.interfaces.db import IAsyncUnitOfWork
from app.modules.canonical.ports.object_repository import CanonicalObjectRepositoryPort
from app.modules.canonical.ports.rule_repository import CanonicalRuleRepositoryPort
from app.modules.canonical.ports.snapshot_repository import (
    CanonicalSnapshotRepositoryPort,
)
from app.modules.canonical.ports.zone_repository import CanonicalZoneRepositoryPort


class CanonicalUoWPort(IAsyncUnitOfWork):
    """Transactional aggregate of canonical repositories.

    Write flows (`SaveCanonicalSnapshotUseCase`) and read flows share this
    protocol to keep persistence details inside adapters.
    """

    snapshots: CanonicalSnapshotRepositoryPort
    zones: CanonicalZoneRepositoryPort
    objects: CanonicalObjectRepositoryPort
    rules: CanonicalRuleRepositoryPort
