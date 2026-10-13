from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.settings.csp_profiles.domain.enums import CertificateBundleFormat


@dataclass(frozen=True, slots=True)
class CSPProfileDTO:
    id: UUID
    name: str
    base_url: str
    username: str
    is_active: bool
    auth_type: str
    has_password: bool
    has_certificate: bool
    certificate_sha256: str
    certificate_not_after: datetime
    certificate_has_private_key: bool
    is_connectable: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CertificateBundleDTO:
    data: bytes
    format: CertificateBundleFormat
    passphrase: str | None
