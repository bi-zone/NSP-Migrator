from __future__ import annotations

import base64

import pytest
from pydantic import SecretStr

from app.core.config.app_settings import ApplicationSettings
from app.core.config.csp_credentials import CSPCredentialsConfig
from app.modules.settings.csp_profiles.domain.entities import CSPProfile
from app.modules.settings.csp_profiles.domain.enums import CertificateBundleFormat
from app.modules.settings.csp_profiles.domain.exceptions import (
    InvalidCSPProfileError,
)


def test_master_key_config_decodes_active_key() -> None:
    active = base64.b64encode(b"a" * 32).decode()
    previous = base64.b64encode(b"b" * 32).decode()

    config = CSPCredentialsConfig.from_settings(
        active_key=SecretStr(active),
    )

    assert config.active_key.get_secret_value() == b"a" * 32
    assert active not in repr(config)


@pytest.mark.parametrize(
    "encoded",
    ["not-base64", base64.b64encode(b"short").decode()],
)
def test_master_key_config_rejects_invalid_key_without_echo(encoded: str) -> None:
    with pytest.raises(ValueError) as raised:
        CSPCredentialsConfig.from_settings(
            active_key=SecretStr(encoded),
        )

    assert encoded not in str(raised.value)


def test_application_settings_validate_master_key_at_startup() -> None:
    with pytest.raises(ValueError):
        ApplicationSettings(
            csp_master_key=SecretStr(base64.b64encode(b"short").decode()),
        )


def test_profile_factory_normalizes_values_and_keeps_secrets_out() -> None:
    profile = CSPProfile.create(
        name="  Production  ",
        base_url="https://CSP.EXAMPLE/",
        username=" admin ",
    )

    assert profile.name == "Production"
    assert profile.base_url == "https://csp.example"
    assert profile.username == "admin"
    assert not hasattr(profile, "password")
    assert not hasattr(profile, "certificate_pem")


@pytest.mark.parametrize(
    "base_url",
    [
        "http://csp.example",
        "https://user@csp.example",
        "https://csp.example/path",
        "https://csp.example?query=1",
    ],
)
def test_profile_factory_rejects_unsafe_base_url(base_url: str) -> None:
    with pytest.raises(InvalidCSPProfileError):
        CSPProfile.create(name="name", base_url=base_url, username="admin")


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("client.pem", CertificateBundleFormat.PEM),
        ("/tmp/client.P12", CertificateBundleFormat.PKCS12),
        (r"C:\certs\client.pfx", CertificateBundleFormat.PKCS12),
    ],
)
def test_bundle_format_from_filename(
    filename: str,
    expected: CertificateBundleFormat,
) -> None:
    assert CertificateBundleFormat.from_filename(filename) is expected


def test_bundle_format_from_filename_rejects_unknown_suffix() -> None:
    with pytest.raises(ValueError, match="pem"):
        CertificateBundleFormat.from_filename("client.txt")
    with pytest.raises(ValueError, match="pem"):
        CertificateBundleFormat.from_filename("client")
