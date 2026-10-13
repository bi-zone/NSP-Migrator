"""CSP profile integration-test fixtures.

This module wires the real CSP profile database adapters, unit of work, and
credential codec against the shared test database. It keeps CSP-specific setup
out of the global integration fixtures while letting tests exercise real
persistence, encryption, and transactional behavior.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pydantic import SecretBytes

from app.core.config.csp_credentials import CSPCredentialsConfig
from app.infrastructure.db.session_factory import SQLAlchemySessionFactory
from app.modules.settings.csp_profiles.adapters.db.uow import CSPProfilesUnitOfWork
from app.modules.settings.csp_profiles.adapters.security.aes_gcm_credential_codec import (
    AESGCMCredentialCodec,
)
from app.modules.settings.csp_profiles.adapters.security.certificate_bundle_converter import (
    CryptographyCertificateBundleConverter,
)
from app.modules.settings.csp_profiles.adapters.security.pem_inspector import (
    PEMCertificateInspector,
)
from app.modules.settings.csp_profiles.application.change_profile_active_status import (
    ChangeProfileActiveStatusUseCase,
)
from app.modules.settings.csp_profiles.application.check_profile_connection import (
    TestProfileConnectionUseCase,
)
from app.modules.settings.csp_profiles.application.create_profile import (
    CreateProfileCommand,
    CreateProfileUseCase,
)
from app.modules.settings.csp_profiles.application.delete_profile import (
    DeleteProfileUseCase,
)
from app.modules.settings.csp_profiles.application.dto import CertificateBundleDTO
from app.modules.settings.csp_profiles.application.get_profile import GetProfileUseCase
from app.modules.settings.csp_profiles.application.list_profiles import (
    ListProfilesUseCase,
)
from app.modules.settings.csp_profiles.application.remove_profile_password import (
    RemoveProfilePasswordUseCase,
)
from app.modules.settings.csp_profiles.application.update_profile import (
    UpdateProfileUseCase,
)
from app.modules.settings.csp_profiles.domain.entities import CSPProfile
from app.modules.settings.csp_profiles.domain.enums import CertificateBundleFormat
from app.modules.settings.csp_profiles.domain.exceptions import (
    CSPProfileAuthenticationError,
    CSPProfileConnectionError,
)
from app.modules.settings.csp_profiles.domain.value_objects import ProfileCredentials
from app.modules.settings.csp_profiles.ports.connection_tester import AllowedVPC

ConnectionMode = Literal["success", "auth", "unavailable", "timeout"]


@dataclass(slots=True)
class RecordingConnectionTester:
    """Fake CSP boundary that records decrypted credentials passed by the use case."""

    mode: ConnectionMode = "success"
    seen_profile: CSPProfile | None = None
    seen_credentials: ProfileCredentials | None = None

    async def test(
        self,
        profile: CSPProfile,
        credentials: ProfileCredentials,
    ) -> list[AllowedVPC]:
        self.seen_profile = profile
        self.seen_credentials = credentials
        if self.mode == "auth":
            raise CSPProfileAuthenticationError
        if self.mode in {"unavailable", "timeout"}:
            raise CSPProfileConnectionError
        return [
            AllowedVPC(
                vpc_id="vpc-1",
                customer_name="Customer",
                project_name="Project",
                cuid="cuid",
                pid="pid",
            )
        ]


@pytest.fixture
def credentials_config() -> CSPCredentialsConfig:
    """Use a stable in-memory master key for deterministic credential tests."""
    return CSPCredentialsConfig(active_key=SecretBytes(b"i" * 32))


@pytest.fixture
def credential_codec(
    credentials_config: CSPCredentialsConfig,
) -> AESGCMCredentialCodec:
    """Build the real AES-GCM codec used by the SQLAlchemy credential store."""
    return AESGCMCredentialCodec(credentials_config)


@pytest.fixture
def csp_profiles_uow_factory(
    session_factory: SQLAlchemySessionFactory,
    credential_codec: AESGCMCredentialCodec,
) -> Callable[[], CSPProfilesUnitOfWork]:
    """Return fresh CSP profile UoWs so each use case owns its transaction."""

    def _factory() -> CSPProfilesUnitOfWork:
        return CSPProfilesUnitOfWork(session_factory, credential_codec)

    return _factory


@pytest.fixture
def combined_client_pem() -> str:
    """Return a valid combined client certificate and private-key PEM bundle."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "integration-client")]
    )
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    return (
        certificate.public_bytes(serialization.Encoding.PEM)
        + key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    ).decode()


@pytest.fixture
def profile_command_factory(
    combined_client_pem: str,
) -> Callable[..., CreateProfileCommand]:
    """Return a factory for standard valid create-profile commands."""

    def _factory(
        *,
        name: str = "Primary",
        base_url: str = "https://csp.example",
        username: str = "operator",
        password: str = "initial-password",
        certificate_pem: str | None = None,
        certificate_bundle: bytes | None = None,
        certificate_passphrase: str | None = None,
        certificate_format: CertificateBundleFormat = CertificateBundleFormat.PEM,
    ) -> CreateProfileCommand:
        bundle = certificate_bundle
        if bundle is None:
            bundle = (certificate_pem or combined_client_pem).encode("utf-8")
        return CreateProfileCommand(
            name=name,
            base_url=base_url,
            username=username,
            password=password,
            certificate_bundle=CertificateBundleDTO(
                data=bundle,
                format=certificate_format,
                passphrase=certificate_passphrase,
            ),
        )

    return _factory


@pytest.fixture
def certificate_inspector() -> PEMCertificateInspector:
    """Use the real PEM inspector so metadata comes from the provided bundle."""
    return PEMCertificateInspector()


@pytest.fixture
def certificate_converter() -> CryptographyCertificateBundleConverter:
    """Use the real bundle converter so create/update accept PEM and PKCS#12."""
    return CryptographyCertificateBundleConverter()


@pytest.fixture
def create_profile_use_case(
    csp_profiles_uow_factory: Callable[[], CSPProfilesUnitOfWork],
    certificate_inspector: PEMCertificateInspector,
    certificate_converter: CryptographyCertificateBundleConverter,
) -> CreateProfileUseCase:
    """Create the real profile creation use case with real DB adapters."""
    return CreateProfileUseCase(
        csp_profiles_uow_factory(),
        certificate_inspector,
        certificate_converter,
    )


@pytest.fixture
def update_profile_use_case(
    csp_profiles_uow_factory: Callable[[], CSPProfilesUnitOfWork],
    certificate_inspector: PEMCertificateInspector,
    certificate_converter: CryptographyCertificateBundleConverter,
) -> UpdateProfileUseCase:
    """Create the real profile update use case with real DB adapters."""
    return UpdateProfileUseCase(
        csp_profiles_uow_factory(),
        certificate_inspector,
        certificate_converter,
    )


@pytest.fixture
def change_profile_active_status_use_case(
    csp_profiles_uow_factory: Callable[[], CSPProfilesUnitOfWork],
) -> ChangeProfileActiveStatusUseCase:
    """Create the real profile change status use case with real DB adapters."""
    return ChangeProfileActiveStatusUseCase(csp_profiles_uow_factory())


@pytest.fixture
def delete_profile_use_case(
    csp_profiles_uow_factory: Callable[[], CSPProfilesUnitOfWork],
) -> DeleteProfileUseCase:
    """Create the real profile deletion use case with real DB adapters."""
    return DeleteProfileUseCase(csp_profiles_uow_factory())


@pytest.fixture
def remove_profile_password_use_case(
    csp_profiles_uow_factory: Callable[[], CSPProfilesUnitOfWork],
) -> RemoveProfilePasswordUseCase:
    """Create the real password-removal use case with real DB adapters."""
    return RemoveProfilePasswordUseCase(csp_profiles_uow_factory())


@pytest.fixture
def get_profile_use_case(
    csp_profiles_uow_factory: Callable[[], CSPProfilesUnitOfWork],
) -> GetProfileUseCase:
    """Create the real profile retrieval use case with real DB adapters."""
    return GetProfileUseCase(csp_profiles_uow_factory())


@pytest.fixture
def list_profiles_use_case(
    csp_profiles_uow_factory: Callable[[], CSPProfilesUnitOfWork],
) -> ListProfilesUseCase:
    """Create the real profile listing use case with real DB adapters."""
    return ListProfilesUseCase(csp_profiles_uow_factory())


@pytest.fixture
def connection_tester_factory() -> Callable[
    [ConnectionMode], RecordingConnectionTester
]:
    """Return fake connection testers configured for success or typed failures."""

    def _factory(mode: ConnectionMode = "success") -> RecordingConnectionTester:
        return RecordingConnectionTester(mode=mode)

    return _factory


@pytest.fixture
def connection_use_case_factory(
    csp_profiles_uow_factory: Callable[[], CSPProfilesUnitOfWork],
    connection_tester_factory: Callable[[ConnectionMode], RecordingConnectionTester],
) -> Callable[[ConnectionMode], TestProfileConnectionUseCase]:
    """Return connection-check use cases wired to real DB state and fake CSP I/O."""

    def _factory(mode: ConnectionMode = "success") -> TestProfileConnectionUseCase:
        return TestProfileConnectionUseCase(
            csp_profiles_uow_factory(),
            connection_tester_factory(mode),
        )

    return _factory


@pytest.fixture
def create_persisted_profile(
    csp_profiles_uow_factory: Callable[[], CSPProfilesUnitOfWork],
    certificate_inspector: PEMCertificateInspector,
    certificate_converter: CryptographyCertificateBundleConverter,
    profile_command_factory: Callable[..., CreateProfileCommand],
) -> Callable[..., object]:
    """Return a helper that persists a profile through the real create use case."""

    async def _create(**overrides):
        use_case = CreateProfileUseCase(
            csp_profiles_uow_factory(),
            certificate_inspector,
            certificate_converter,
        )
        return await use_case.execute(profile_command_factory(**overrides))

    return _create
