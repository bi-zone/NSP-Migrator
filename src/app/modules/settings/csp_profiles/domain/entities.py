from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Self
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

from app.modules.settings.csp_profiles.domain.exceptions import (
    InvalidCSPProfileError,
)
from app.modules.settings.csp_profiles.domain.value_objects import (
    StoredCredentialMetadata,
)


@dataclass(frozen=True, slots=True)
class CSPProfile:
    """Secret-free aggregate describing one CSP connection target."""

    id: UUID
    name: str
    base_url: str
    username: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    credential_metadata: StoredCredentialMetadata | None = None

    @classmethod
    def create(cls, *, name: str, base_url: str, username: str) -> Self:
        now = datetime.now(UTC)
        return cls(
            id=uuid4(),
            name=_required_trimmed(name, maximum=128),
            base_url=_normalize_base_url(base_url),
            username=_required_trimmed(username, maximum=255),
            is_active=True,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_connectable(self) -> bool:
        metadata = self.credential_metadata
        return bool(
            metadata
            and metadata.has_certificate
            and metadata.certificate_has_private_key
        )

    def attach_credential_metadata(self, metadata: StoredCredentialMetadata) -> Self:
        return replace(self, credential_metadata=metadata)

    def update(
        self,
        *,
        name: str | None = None,
        base_url: str | None = None,
        username: str | None = None,
        credential_metadata: StoredCredentialMetadata | None = None,
    ) -> Self:
        updated_name = (
            self.name if name is None else _required_trimmed(name, maximum=128)
        )
        updated_url = (
            self.base_url if base_url is None else _normalize_base_url(base_url)
        )
        updated_username = (
            self.username
            if username is None
            else _required_trimmed(username, maximum=255)
        )
        return replace(
            self,
            name=updated_name,
            base_url=updated_url,
            username=updated_username,
            updated_at=datetime.now(UTC),
            credential_metadata=credential_metadata or self.credential_metadata,
        )


def _required_trimmed(value: str, *, maximum: int) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise InvalidCSPProfileError
    return normalized


def _normalize_base_url(value: str) -> str:
    candidate = value.strip()
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise InvalidCSPProfileError from exc
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise InvalidCSPProfileError
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    netloc = f"{host}:{port}" if port is not None else host
    return urlunsplit((parsed.scheme, netloc, "", "", ""))
