from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.execute.domain.entities import ExecutePlanRule


class ReportsWriterPort(ABC):
    """Execute-owned seam for recording one completed plan as a report."""

    @abstractmethod
    async def save_report(
        self,
        *,
        scope_title: str,
        csp_profile_id: UUID,
        vpc_id: str,
        target_id: str,
        commit_id: int,
        plan_rules: list[ExecutePlanRule],
    ) -> None: ...
