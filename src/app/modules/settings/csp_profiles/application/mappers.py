from app.modules.settings.csp_profiles.application.dto import CSPProfileDTO
from app.modules.settings.csp_profiles.domain.entities import CSPProfile
from app.modules.settings.csp_profiles.domain.exceptions import (
    CSPProfileConnectionValidationError,
    InvalidCertificateBundleError,
)
from app.modules.settings.csp_profiles.domain.value_objects import (
    ProfileCredentials,
    StoredCredentialMetadata,
)
from app.modules.settings.csp_profiles.ports.certificate_inspector import (
    CertificateInspectorPort,
)
from app.modules.settings.csp_profiles.ports.credential_store import CredentialWrite


def profile_to_dto(profile: CSPProfile) -> CSPProfileDTO:
    metadata = profile.credential_metadata
    if metadata is None:
        raise CSPProfileConnectionValidationError
    return CSPProfileDTO(
        id=profile.id,
        name=profile.name,
        base_url=profile.base_url,
        username=profile.username,
        is_active=profile.is_active,
        auth_type="password_mtls" if metadata.has_password else "mtls",
        has_password=metadata.has_password,
        has_certificate=metadata.has_certificate,
        certificate_sha256=metadata.certificate_sha256,
        certificate_not_after=metadata.certificate_not_after,
        certificate_has_private_key=metadata.certificate_has_private_key,
        is_connectable=profile.is_connectable,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def credentials_to_write(
    *,
    certificate_pem: str,
    password: str | None,
    inspector: CertificateInspectorPort,
    require_private_key: bool = False,
) -> CredentialWrite:
    certificate = inspector.inspect(certificate_pem)
    if require_private_key and not certificate.has_private_key:
        raise InvalidCertificateBundleError
    return CredentialWrite(
        credentials=ProfileCredentials(
            certificate_pem=certificate_pem,
            password=password,
        ),
        metadata=StoredCredentialMetadata(
            has_password=password is not None,
            has_certificate=True,
            certificate_sha256=certificate.sha256,
            certificate_not_after=certificate.not_after,
            certificate_has_private_key=certificate.has_private_key,
        ),
    )
