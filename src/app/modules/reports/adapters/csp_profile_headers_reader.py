from uuid import UUID

from app.modules.reports.domain.exceptions import ReportsModuleNotFoundError
from app.modules.reports.ports.csp_profile_headers_reader import (
    CSPProfileHeaderDTO,
    CSPProfileHeadersReaderPort,
)
from app.modules.settings.csp_profiles.application.get_profile import (
    GetProfileQuery,
    GetProfileUseCase,
)
from app.modules.settings.csp_profiles.application.list_profiles import (
    ListProfilesQuery,
    ListProfilesResult,
    ListProfilesUseCase,
)
from app.modules.settings.csp_profiles.domain.exceptions import CSPProfileNotFoundError


class SettingsCSPProfileHeadersReader(CSPProfileHeadersReaderPort):
    """Adapt Settings profile reads for Reports header presentation."""

    def __init__(
        self,
        list_profiles_use_case: ListProfilesUseCase,
        get_profile_use_case: GetProfileUseCase,
    ) -> None:
        self._list_profiles_use_case = list_profiles_use_case
        self._get_profile_use_case = get_profile_use_case

    async def get_header_by_id(self, profile_id: UUID) -> CSPProfileHeaderDTO:
        """Project one Settings profile into the lightweight Reports header."""
        try:
            profile = await self._get_profile_use_case.execute(
                GetProfileQuery(profile_id=profile_id)
            )
        except CSPProfileNotFoundError as error:
            raise ReportsModuleNotFoundError(
                f"CSP profile {profile_id} not found"
            ) from error
        return CSPProfileHeaderDTO(
            id=profile.id,
            name=profile.name,
            base_url=profile.base_url,
        )

    async def get_headers_by_ids(
        self,
        profile_ids: tuple[UUID, ...],
    ) -> tuple[CSPProfileHeaderDTO, ...]:
        if not profile_ids:
            return ()

        result: ListProfilesResult = await self._list_profiles_use_case.execute(
            ListProfilesQuery(profile_ids=profile_ids)
        )
        headers = tuple(
            CSPProfileHeaderDTO(
                id=profile.id,
                name=profile.name,
                base_url=profile.base_url,
            )
            for profile in result.profiles
        )
        found_ids = {header.id for header in headers}
        missing_ids = set(profile_ids) - found_ids
        if missing_ids:
            raise ReportsModuleNotFoundError(f"CSP profiles not found: {missing_ids}")
        return headers
