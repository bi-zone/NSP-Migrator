from __future__ import annotations

from dataclasses import dataclass, field

from app.infrastructure.db.transactional import async_transactional
from app.modules.settings.csp_profiles.application.dto import (
    CertificateBundleDTO,
    CSPProfileDTO,
)
from app.modules.settings.csp_profiles.application.mappers import (
    credentials_to_write,
    profile_to_dto,
)
from app.modules.settings.csp_profiles.domain.entities import CSPProfile
from app.modules.settings.csp_profiles.domain.exceptions import (
    DuplicateCSPProfileNameError,
    InvalidCSPProfileError,
)
from app.modules.settings.csp_profiles.ports.certificate_bundle_converter import (
    CertificateBundleConverterPort,
)
from app.modules.settings.csp_profiles.ports.certificate_inspector import (
    CertificateInspectorPort,
)
from app.modules.settings.csp_profiles.ports.uow import CSPProfilesUnitOfWorkPort


@dataclass(frozen=True, slots=True)
class CreateProfileCommand:
    name: str
    base_url: str
    username: str
    password: str = field(repr=False)
    certificate_bundle: CertificateBundleDTO


class CreateProfileUseCase:
    def __init__(
        self,
        uow: CSPProfilesUnitOfWorkPort,
        certificate_inspector: CertificateInspectorPort,
        certificate_converter: CertificateBundleConverterPort,
    ) -> None:
        self.uow = uow
        self._certificate_inspector = certificate_inspector
        self._certificate_converter = certificate_converter

    @async_transactional()
    async def execute(self, command: CreateProfileCommand) -> CSPProfileDTO:
        if not command.certificate_bundle.data:
            raise InvalidCSPProfileError
        if not command.password:
            raise InvalidCSPProfileError
        if await self.uow.profiles.get_by_name(command.name) is not None:
            raise DuplicateCSPProfileNameError

        profile = CSPProfile.create(
            name=command.name,
            base_url=command.base_url,
            username=command.username,
        )
        certificate_pem = self._certificate_converter.convert(
            command.certificate_bundle
        )
        credential_write = credentials_to_write(
            certificate_pem=certificate_pem,
            password=command.password,
            inspector=self._certificate_inspector,
            require_private_key=True,
        )
        await self.uow.profiles.save(profile)
        await self.uow.credentials.put_for_profile(profile.id, credential_write)
        return profile_to_dto(
            profile.attach_credential_metadata(credential_write.metadata)
        )
