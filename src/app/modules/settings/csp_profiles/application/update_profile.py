from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

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
    CSPProfileNotFoundError,
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


class UnsetType:
    __slots__ = ()

    def __repr__(self) -> str:
        return "UNSET"


UNSET = UnsetType()


@dataclass(frozen=True, slots=True)
class UpdateProfileCommand:
    profile_id: UUID
    name: str | None | UnsetType = UNSET
    base_url: str | None | UnsetType = UNSET
    username: str | None | UnsetType = UNSET
    password: str | None | UnsetType = field(default=UNSET, repr=False)
    certificate_bundle: CertificateBundleDTO | UnsetType = field(
        default=UNSET, repr=False
    )


class UpdateProfileUseCase:
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
    async def execute(self, command: UpdateProfileCommand) -> CSPProfileDTO:
        _validate_command(command)
        profile: CSPProfile | None = await self.uow.profiles.get_by_id(
            command.profile_id
        )
        if profile is None:
            raise CSPProfileNotFoundError

        name = _value_or_none(command.name)
        if name is not None and name.casefold() != profile.name.casefold():
            duplicate = await self.uow.profiles.get_by_name(name)
            if duplicate is not None and duplicate.id != profile.id:
                raise DuplicateCSPProfileNameError

        credential_write = None
        if not isinstance(command.certificate_bundle, UnsetType) or not isinstance(
            command.password, UnsetType
        ):
            current = await self.uow.credentials.get_for_connection(profile.id)
            if current is None:
                raise InvalidCSPProfileError
            if isinstance(command.certificate_bundle, UnsetType):
                certificate_pem = current.certificate_pem
                require_private_key = False
            else:
                certificate_pem = self._new_certificate_pem(command)
                require_private_key = True
            password = (
                current.password
                if isinstance(command.password, UnsetType)
                else command.password
            )
            if certificate_pem is None or (
                password is None and not isinstance(command.password, UnsetType)
            ):
                raise InvalidCSPProfileError
            credential_write = credentials_to_write(
                certificate_pem=certificate_pem,
                password=password,
                inspector=self._certificate_inspector,
                require_private_key=require_private_key,
            )

        updated = profile.update(
            name=name,
            base_url=_value_or_none(command.base_url),
            username=_value_or_none(command.username),
            credential_metadata=(
                credential_write.metadata if credential_write is not None else None
            ),
        )

        # update profile data
        profile_updated: bool = await self.uow.profiles.update(updated)
        if not profile_updated:
            raise CSPProfileNotFoundError

        # update creds, if new provided
        if credential_write is not None:
            await self.uow.credentials.put_for_profile(profile.id, credential_write)

        return profile_to_dto(updated)

    def _new_certificate_pem(self, command: UpdateProfileCommand) -> str:
        if isinstance(command.certificate_bundle, UnsetType) or not isinstance(
            command.certificate_bundle.data, bytes
        ):
            raise InvalidCSPProfileError

        return self._certificate_converter.convert(
            command.certificate_bundle,
        )


def _validate_command(command: UpdateProfileCommand) -> None:
    values = (
        command.name,
        command.base_url,
        command.username,
        command.certificate_bundle,
        command.password,
    )
    if all(isinstance(value, UnsetType) for value in values):
        raise InvalidCSPProfileError

    for value in values:
        if isinstance(value, UnsetType):
            continue
        if _is_blank(value):
            raise InvalidCSPProfileError


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, bytes):
        return not value
    if isinstance(value, str):
        return not value.strip()
    return False


def _value_or_none(value: str | None | UnsetType) -> str | None:
    return None if isinstance(value, UnsetType) else value
