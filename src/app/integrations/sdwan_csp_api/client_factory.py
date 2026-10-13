from __future__ import annotations

import os
import ssl
import tempfile
from pathlib import Path

from app.infrastructure.http_requester.requester import HttpxRequester
from app.integrations.sdwan_csp_api.client import SDWANCspHttpClient
from app.modules.settings.csp_profiles.domain.entities import CSPProfile
from app.modules.settings.csp_profiles.domain.exceptions import (
    CSPProfileConnectionValidationError,
)
from app.modules.settings.csp_profiles.domain.value_objects import ProfileCredentials


class SDWANClientFactory:
    """Build one isolated SD-WAN client from a profile snapshot."""

    def __init__(self, *, timeout_seconds: float = 20.0) -> None:
        self._timeout_seconds = timeout_seconds

    def create(
        self,
        *,
        profile: CSPProfile,
        credentials: ProfileCredentials,
        vpc_id: str | None,
    ) -> SDWANCspHttpClient:
        # Pre-profile wiring: verify=False + httpx cert=path (not SSLContext).
        cert_path = self._materialize_client_cert(credentials.certificate_pem)
        requester = HttpxRequester(
            verify_server_ssl=False,
            cert_path=str(cert_path),
            timeout=self._timeout_seconds,
            owned_cert_path=str(cert_path),
        )
        return SDWANCspHttpClient(
            base_url=profile.base_url,
            username=profile.username,
            password=credentials.password or "",
            vpc_id=vpc_id,
            requester=requester,
        )

    @staticmethod
    def _materialize_client_cert(certificate_pem: str) -> Path:
        descriptor, raw_path = tempfile.mkstemp(
            prefix="csp-profile-",
            suffix=".pem",
        )
        path = Path(raw_path)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as pem_file:
                descriptor = -1
                payload = certificate_pem.encode("utf-8")
                pem_file.write(payload)
                if not payload.endswith(b"\n"):
                    pem_file.write(b"\n")

            # Fail fast on unusable bundles; httpx will re-read the same file.
            probe = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            probe.load_cert_chain(str(path))
            return path
        except Exception:
            if descriptor >= 0:
                os.close(descriptor)
            path.unlink(missing_ok=True)
            raise CSPProfileConnectionValidationError from None
