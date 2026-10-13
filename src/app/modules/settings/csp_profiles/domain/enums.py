from __future__ import annotations

from enum import StrEnum


class CertificateBundleFormat(StrEnum):
    """Declared ingest format for a client certificate bundle."""

    PEM = "pem"
    PKCS12 = "pkcs12"

    @classmethod
    def from_filename(cls, filename: str) -> CertificateBundleFormat:
        suffix = _filename_suffix(filename)
        if suffix == "pem":
            return cls.PEM
        if suffix in {"p12", "pfx"}:
            return cls.PKCS12
        raise ValueError("Certificate file must be .pem, .p12, or .pfx")


def _filename_suffix(filename: str) -> str:
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].strip()
    if "." not in name or name.startswith("."):
        return ""
    return name.rsplit(".", 1)[-1].lower()
