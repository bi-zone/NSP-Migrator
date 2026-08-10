from app.infrastructure.db.uow import SQLAlchemyUnitOfWork
from app.modules.canonical.adapters.db.object_repository import (
    SQLAlchemyCanonicalObjectRepository,
)
from app.modules.canonical.adapters.db.rule_repository import (
    SQLAlchemyCanonicalRuleRepository,
)
from app.modules.canonical.adapters.db.snapshot_repository import (
    SQLAlchemyCanonicalSnapshotRepository,
)
from app.modules.canonical.adapters.db.zone_repository import (
    SQLAlchemyCanonicalZoneRepository,
)
from app.modules.canonical.ports.uow import CanonicalUoWPort


# TODO:: check
class CanonicalUoW(SQLAlchemyUnitOfWork, CanonicalUoWPort):
    def bind_repositories(self) -> None:
        if self.session is None:
            raise RuntimeError("CanonicalUoW session is not initialized")
        self.snapshots = SQLAlchemyCanonicalSnapshotRepository(self.session)
        self.zones = SQLAlchemyCanonicalZoneRepository(self.session)
        self.objects = SQLAlchemyCanonicalObjectRepository(self.session)
        self.rules = SQLAlchemyCanonicalRuleRepository(self.session)

    async def __aenter__(self):
        await super().__aenter__()
        self.bind_repositories()
        return self
