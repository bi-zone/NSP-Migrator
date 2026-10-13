from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from app.modules.settings.csp_profiles.application.check_profile_connection import (
    TestProfileConnectionCommand as ConnectionCommand,
)
from app.modules.settings.csp_profiles.application.check_profile_connection import (
    TestProfileConnectionUseCase as ConnectionUseCase,
)
from app.modules.settings.csp_profiles.application.create_profile import (
    CreateProfileCommand,
    CreateProfileUseCase,
)
from app.modules.settings.csp_profiles.application.delete_profile import (
    DeleteProfileCommand,
    DeleteProfileUseCase,
)
from app.modules.settings.csp_profiles.application.list_profiles import (
    ListProfilesQuery,
    ListProfilesUseCase,
)
from app.modules.settings.csp_profiles.application.dto import CertificateBundleDTO
from app.modules.settings.csp_profiles.application.remove_profile_password import (
    RemoveProfilePasswordCommand,
    RemoveProfilePasswordUseCase,
)
from app.modules.settings.csp_profiles.application.update_profile import (
    UpdateProfileCommand,
    UpdateProfileUseCase,
)
from app.modules.settings.csp_profiles.domain.entities import CSPProfile
from app.modules.settings.csp_profiles.domain.enums import CertificateBundleFormat
from app.modules.settings.csp_profiles.domain.exceptions import (
    DuplicateCSPProfileNameError,
    InvalidCertificateBundleError,
    InvalidCSPProfileError,
)
from app.modules.settings.csp_profiles.domain.value_objects import (
    CertificateMetadata,
    ProfileCredentials,
    StoredCredentialMetadata,
)
from app.modules.settings.csp_profiles.ports.connection_tester import AllowedVPC
from app.modules.settings.csp_profiles.ports.credential_store import CredentialWrite


class _Profiles:
    def __init__(self) -> None:
        self.items: dict = {}

    async def save(self, profile):
        self.items[profile.id] = profile

    async def update(self, profile):
        self.items[profile.id] = profile
        return True

    async def get_by_id(self, profile_id):
        return self.items.get(profile_id)

    async def get_by_name(self, name):
        normalized = name.strip().casefold()
        return next(
            (
                profile
                for profile in self.items.values()
                if profile.name.casefold() == normalized
            ),
            None,
        )

    async def list_all(self, active_only=False, profile_ids=None):
        profiles = list(self.items.values())
        if active_only:
            profiles = [profile for profile in profiles if profile.is_active]
        if profile_ids is not None:
            profiles = [profile for profile in profiles if profile.id in profile_ids]
        return profiles

    async def delete(self, profile_id):
        del self.items[profile_id]
        return True


class _Credentials:
    def __init__(self) -> None:
        self.items: dict = {}

    async def put_for_profile(self, profile_id, credential_write: CredentialWrite):
        self.items[profile_id] = credential_write.credentials

    async def replace_explicit(self, profile_id, credential_write):
        self.items[profile_id] = credential_write.credentials

    async def get_for_connection(self, profile_id):
        return self.items.get(profile_id)

    async def remove_password(self, profile_id):
        current = self.items[profile_id]
        self.items[profile_id] = ProfileCredentials(
            certificate_pem=current.certificate_pem,
            password=None,
        )

    async def delete_for_profile(self, profile_id):
        self.items.pop(profile_id, None)


class _Uow:
    def __init__(self) -> None:
        self.session = None
        self.profiles = _Profiles()
        self.credentials = _Credentials()
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def __call__(self, reuse_session=False):
        return self

    async def commit(self):
        self.commits += 1


class _Inspector:
    def inspect(self, certificate_pem):
        return CertificateMetadata(
            sha256="a" * 64,
            not_after=datetime(2030, 1, 1, tzinfo=UTC),
            has_private_key=True,
        )


class _Converter:
    def convert(self, bundle: CertificateBundleDTO) -> str:
        return bundle.data.decode()


class _NoKeyInspector:
    def inspect(self, certificate_pem):
        return CertificateMetadata(
            sha256="a" * 64,
            not_after=datetime(2030, 1, 1, tzinfo=UTC),
            has_private_key=False,
        )


class _ConnectionTester:
    async def test(self, profile, credentials):
        assert credentials.password is None
        return [
            AllowedVPC(
                vpc_id="vpc-1",
                customer_name="Customer",
                project_name="Project",
                cuid="cuid",
                pid="pid",
            )
        ]


def _profile(*, password: str | None = "old-password") -> tuple[_Uow, CSPProfile]:
    uow = _Uow()
    profile = CSPProfile.create(
        name="Primary",
        base_url="https://csp.example",
        username="operator",
    ).attach_credential_metadata(
        StoredCredentialMetadata(
            has_password=password is not None,
            has_certificate=True,
            certificate_sha256="a" * 64,
            certificate_not_after=datetime(2030, 1, 1, tzinfo=UTC),
            certificate_has_private_key=True,
        )
    )
    uow.profiles.items[profile.id] = profile
    uow.credentials.items[profile.id] = ProfileCredentials(
        certificate_pem="CERTIFICATE",
        password=password,
    )
    return uow, profile


def test_create_profile_is_atomic_and_rejects_duplicate_name():
    uow = _Uow()
    use_case = CreateProfileUseCase(uow, _Inspector(), _Converter())
    result = asyncio.run(
        use_case.execute(
            CreateProfileCommand(
                name="Primary",
                base_url="https://CSP.EXAMPLE/",
                username="operator",
                password="secret",
                certificate_bundle=CertificateBundleDTO(
                    data=b"CERTIFICATE",
                    format=CertificateBundleFormat.PEM,
                    passphrase=None,
                )
            )
        )
    )

    assert result.base_url == "https://csp.example"
    assert result.auth_type == "password_mtls"
    assert uow.credentials.items[result.id].password == "secret"
    with pytest.raises(DuplicateCSPProfileNameError):
        asyncio.run(
            use_case.execute(
                CreateProfileCommand(
                    name=" primary ",
                    base_url="https://other.example",
                    username="operator",
                    password="secret",
                    certificate_bundle=CertificateBundleDTO(
                        data=b"CERTIFICATE",
                        format=CertificateBundleFormat.PEM,
                        passphrase=None,
                    )
                )
            )
        )


def test_patch_replaces_only_explicit_secret_and_rejects_null_or_empty():
    uow, profile = _profile()
    use_case = UpdateProfileUseCase(uow, _Inspector(), _Converter())
    asyncio.run(
        use_case.execute(
            UpdateProfileCommand(
                profile_id=profile.id,
                password="new-password",
            )
        )
    )
    assert uow.credentials.items[profile.id].certificate_pem == "CERTIFICATE"
    assert uow.credentials.items[profile.id].password == "new-password"

    with pytest.raises(InvalidCSPProfileError):
        asyncio.run(
            use_case.execute(
                UpdateProfileCommand(
                    profile_id=profile.id,
                    password=None,
                )
            )
        )


def test_remove_password_keeps_certificate_and_connection_test_is_safe():
    uow, profile = _profile()
    result = asyncio.run(
        RemoveProfilePasswordUseCase(uow).execute(
            RemoveProfilePasswordCommand(
                profile_id=profile.id,
            )
        )
    )
    assert result.auth_type == "mtls"
    assert uow.credentials.items[profile.id].certificate_pem == "CERTIFICATE"
    connection = asyncio.run(
        ConnectionUseCase(uow, _ConnectionTester()).execute(
            ConnectionCommand(profile_id=profile.id)
        )
    )
    assert connection.reachable is True
    assert connection.authenticated is True
    assert connection.allowed_vpcs[0].vpc_id == "vpc-1"


def test_create_profile_rejects_bundle_without_private_key():
    uow = _Uow()
    use_case = CreateProfileUseCase(uow, _NoKeyInspector(), _Converter())

    with pytest.raises(InvalidCertificateBundleError):
        asyncio.run(
            use_case.execute(
                CreateProfileCommand(
                    name="Primary",
                    base_url="https://csp.example",
                    username="operator",
                    password="secret",
                    certificate_bundle=CertificateBundleDTO(
                        data=b"CERTIFICATE",
                        format=CertificateBundleFormat.PEM,
                        passphrase=None,
                    )
                )
            )
        )


def test_delete_removes_profile_and_credentials():
    uow, profile = _profile()

    asyncio.run(
        DeleteProfileUseCase(uow).execute(DeleteProfileCommand(profile_id=profile.id))
    )
    assert profile.id not in uow.profiles.items
    assert profile.id not in uow.credentials.items


def test_list_profiles_optionally_filters_by_profile_ids():
    uow, included = _profile()
    excluded = CSPProfile.create(
        name="Secondary",
        base_url="https://secondary-csp.example",
        username="operator",
    ).attach_credential_metadata(
        StoredCredentialMetadata(
            has_password=False,
            has_certificate=True,
            certificate_sha256="b" * 64,
            certificate_not_after=datetime(2030, 1, 1, tzinfo=UTC),
            certificate_has_private_key=True,
        )
    )
    uow.profiles.items[excluded.id] = excluded

    use_case = ListProfilesUseCase(uow)

    all_profiles = asyncio.run(use_case.execute(ListProfilesQuery()))
    filtered_profiles = asyncio.run(
        use_case.execute(ListProfilesQuery(profile_ids=(included.id,)))
    )
    empty_filter = asyncio.run(use_case.execute(ListProfilesQuery(profile_ids=())))

    assert {profile.id for profile in all_profiles.profiles} == {
        included.id,
        excluded.id,
    }
    assert [profile.id for profile in filtered_profiles.profiles] == [included.id]
    assert empty_filter.profiles == []
