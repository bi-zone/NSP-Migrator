from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import Protocol

from app.modules.settings.csp_profiles.domain.entities import CSPProfile
from app.modules.settings.csp_profiles.domain.value_objects import ProfileCredentials


@dataclass(frozen=True, slots=True)
class AllowedVPC:
    vpc_id: str
    customer_name: str
    project_name: str
    cuid: str
    pid: str


class CSPProfileConnectionTesterPort(Protocol):
    """Connection checks."""

    @abstractmethod
    async def test(
        self,
        profile: CSPProfile,
        credentials: ProfileCredentials,
    ) -> list[AllowedVPC]: ...
