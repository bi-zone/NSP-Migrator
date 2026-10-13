from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.modules.settings.csp_profiles.domain.enums import CertificateBundleFormat
from streamlit_app.views.settings import (
    _read_bundle,
    _read_certificate_passphrase,
    _read_uploaded_certificate,
)


def test_read_bundle_accepts_binary_pkcs12() -> None:
    payload = b"\x30\x82p12-binary"
    uploaded = SimpleNamespace(name="client.p12", getvalue=lambda: payload)

    assert _read_bundle(uploaded) == payload
    bundle, bundle_format = _read_uploaded_certificate(uploaded)
    assert bundle == payload
    assert bundle_format is CertificateBundleFormat.PKCS12


def test_read_uploaded_certificate_maps_pem_and_pfx_extensions() -> None:
    pem = SimpleNamespace(name="client.pem", getvalue=lambda: b"PEM")
    pfx = SimpleNamespace(name="client.pfx", getvalue=lambda: b"PFX")

    assert _read_uploaded_certificate(pem)[1] is CertificateBundleFormat.PEM
    assert _read_uploaded_certificate(pfx)[1] is CertificateBundleFormat.PKCS12


def test_read_uploaded_certificate_rejects_unknown_extension() -> None:
    uploaded = SimpleNamespace(name="client.txt", getvalue=lambda: b"nope")

    with pytest.raises(ValueError, match="pem"):
        _read_uploaded_certificate(uploaded)


def test_read_bundle_rejects_empty_or_missing_file() -> None:
    with pytest.raises(ValueError, match="required"):
        _read_bundle(None)
    with pytest.raises(ValueError, match="empty"):
        _read_bundle(SimpleNamespace(getvalue=lambda: b""))


def test_read_certificate_passphrase_requires_value_only_when_protected() -> None:
    assert _read_certificate_passphrase(protected=False, value="") is None
    assert _read_certificate_passphrase(protected=True, value="secret") == "secret"
    with pytest.raises(ValueError, match="passphrase"):
        _read_certificate_passphrase(protected=True, value="")
