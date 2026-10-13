from __future__ import annotations

import re

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from app.modules.settings.csp_profiles.domain.exceptions import (
    InvalidCertificateBundleError,
)
from app.modules.settings.csp_profiles.domain.value_objects import (
    CertificateMetadata,
)

_PRIVATE_KEY_PATTERN = re.compile(
    rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
)


class PEMCertificateInspector:
    """Derive safe metadata from the combined PEM accepted by the CSP client."""

    def inspect(self, certificate_pem: str) -> CertificateMetadata:
        try:
            pem_bytes = certificate_pem.encode("utf-8")
            certificates = x509.load_pem_x509_certificates(pem_bytes)
            if not certificates:
                raise ValueError
            has_private_key = bool(_PRIVATE_KEY_PATTERN.search(pem_bytes))
            if has_private_key:
                serialization.load_pem_private_key(pem_bytes, password=None)
            leaf = certificates[0]
            return CertificateMetadata(
                sha256=leaf.fingerprint(hashes.SHA256()).hex(),
                not_after=leaf.not_valid_after_utc,
                has_private_key=has_private_key,
            )
        except Exception:
            raise InvalidCertificateBundleError from None
