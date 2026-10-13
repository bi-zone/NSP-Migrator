from __future__ import annotations

from app.modules.settings.csp_profiles.adapters.db.models import (
    CSPProfileCredentialsModel,
    CSPProfileModel,
)
from app.modules.settings.csp_profiles.domain.entities import CSPProfile
from app.modules.settings.csp_profiles.domain.value_objects import (
    StoredCredentialMetadata,
)


def csp_profile_to_model(profile: CSPProfile) -> CSPProfileModel:
    return CSPProfileModel(
        id=profile.id,
        name=profile.name,
        base_url=profile.base_url,
        username=profile.username,
        is_active=profile.is_active,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def csp_profile_from_models(
    profile: CSPProfileModel,
    credentials: CSPProfileCredentialsModel | None = None,
) -> CSPProfile:
    metadata = None
    if credentials is not None:
        metadata = StoredCredentialMetadata(
            has_password=credentials.has_password,
            has_certificate=credentials.has_certificate,
            certificate_sha256=credentials.certificate_sha256,
            certificate_not_after=credentials.certificate_not_after,
            certificate_has_private_key=credentials.certificate_has_private_key,
        )
    return CSPProfile(
        id=profile.id,
        name=profile.name,
        base_url=profile.base_url,
        username=profile.username,
        is_active=profile.is_active,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        credential_metadata=metadata,
    )
