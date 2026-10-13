from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CertificateMetadata:
    """Non-secret metadata derived from a combined client certificate bundle."""

    sha256: str
    not_after: datetime
    has_private_key: bool


@dataclass(frozen=True, slots=True)
class ProfileCredentials:
    """Application-facing plaintext credentials with a redacted representation."""

    certificate_pem: str = field(repr=False)
    password: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class StoredCredentialMetadata:
    """Safe metadata persisted alongside an encrypted credential payload."""

    has_password: bool
    has_certificate: bool
    certificate_sha256: str
    certificate_not_after: datetime
    certificate_has_private_key: bool
