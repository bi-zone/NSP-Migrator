from __future__ import annotations

import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.fastapi.error_handlers import register_exception_handlers
from app.modules.settings.csp_profiles.di.dependencies import (
    create_profile_uc,
    update_profile_uc,
)
from app.modules.settings.csp_profiles.domain.enums import CertificateBundleFormat
from app.modules.settings.http.router import settings_router

_PEM = b"-----BEGIN CERTIFICATE-----\nPEM_MARKER\n-----END CERTIFICATE-----"
_PEM_SHORT = b"-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----"


def _profile():
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        name="Primary",
        base_url="https://csp.example",
        username="operator",
        auth_type="password_mtls",
        has_password=True,
        has_certificate=True,
        certificate_sha256="a" * 64,
        certificate_not_after=now,
        certificate_has_private_key=True,
        is_connectable=True,
        revision=3,
        target_revision=1,
        created_at=now,
        updated_at=now,
    )


class _ResultUseCase:
    def __init__(self, result):
        self.result = result

    async def execute(self, command):
        return self.result


def _client(*, raise_server_exceptions: bool = True):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(
        settings_router,
        prefix="/v1/policy-migrator",
    )
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def _create_form(**overrides: str) -> dict[str, str]:
    data = {
        "name": "Primary",
        "base_url": "https://csp.example",
        "username": "operator",
        "password": "csp-password",
    }
    data.update(overrides)
    return data


def _pem_file(*, content: bytes = _PEM, filename: str = "client.pem"):
    return {"certificate": (filename, content, "application/x-pem-file")}


def test_create_response_and_openapi_never_expose_secrets():
    client = _client()
    client.app.dependency_overrides[create_profile_uc] = lambda: _ResultUseCase(
        _profile()
    )
    password = "PASSWORD_MARKER"
    response = client.post(
        "/v1/policy-migrator/settings/csp-profiles",
        data=_create_form(password=password),
        files=_pem_file(),
    )

    assert response.status_code == 201
    serialized = response.text
    assert password not in serialized
    assert "PEM_MARKER" not in serialized
    response_schema = client.get("/openapi.json").json()["components"]["schemas"][
        "CSPProfileResponse"
    ]
    properties = response_schema["properties"]
    assert "password" not in properties
    assert "certificate_pem" not in properties
    assert "encrypted_payload" not in properties


def test_validation_error_redacts_secret_input_and_context():
    client = _client()
    client.app.dependency_overrides[create_profile_uc] = lambda: _ResultUseCase(
        _profile()
    )
    marker = "PASSWORD_MARKER"
    response = client.post(
        "/v1/policy-migrator/settings/csp-profiles",
        data=_create_form(password=""),
        files=_pem_file(content=_PEM_SHORT),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "request_validation_error"
    assert marker not in response.text
    assert "input" not in response.text
    assert "ctx" not in response.text


def test_generic_error_response_and_logs_do_not_include_exception_message(caplog):
    marker = "SECRET_EXCEPTION_MARKER"
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/explode")
    async def explode():
        raise RuntimeError(marker)

    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR):
        response = client.get("/explode")

    assert response.status_code == 500
    assert marker not in response.text
    assert marker not in caplog.text


class _CapturingUseCase:
    def __init__(self, result):
        self.result = result
        self.command = None

    async def execute(self, command):
        self.command = command
        return self.result


def test_create_accepts_certificate_passphrase_and_keeps_it_out_of_responses():
    client = _client()
    capture = _CapturingUseCase(_profile())
    client.app.dependency_overrides[create_profile_uc] = lambda: capture
    passphrase = "CERT_PASSPHRASE_MARKER"
    response = client.post(
        "/v1/policy-migrator/settings/csp-profiles",
        data=_create_form(certificate_passphrase=passphrase),
        files=_pem_file(content=_PEM_SHORT),
    )

    assert response.status_code == 201
    assert capture.command is not None
    assert capture.command.certificate_bundle.data.startswith(b"-----BEGIN CERTIFICATE-----")
    assert capture.command.certificate_bundle.format is CertificateBundleFormat.PEM
    assert capture.command.certificate_bundle.passphrase == passphrase
    assert passphrase not in response.text
    response_schema = client.get("/openapi.json").json()["components"]["schemas"][
        "CSPProfileResponse"
    ]
    assert "certificate_passphrase" not in response_schema["properties"]


def test_create_reads_pkcs12_file_from_filename():
    client = _client()
    capture = _CapturingUseCase(_profile())
    client.app.dependency_overrides[create_profile_uc] = lambda: capture
    binary = b"\x30\x82pkcs12-bytes"
    response = client.post(
        "/v1/policy-migrator/settings/csp-profiles",
        data=_create_form(),
        files={"certificate": ("client.p12", binary, "application/x-pkcs12")},
    )

    assert response.status_code == 201
    assert capture.command is not None
    assert capture.command.certificate_bundle.data == binary
    assert capture.command.certificate_bundle.format is CertificateBundleFormat.PKCS12


def test_create_rejects_unknown_certificate_extension():
    client = _client()
    client.app.dependency_overrides[create_profile_uc] = lambda: _ResultUseCase(
        _profile()
    )
    response = client.post(
        "/v1/policy-migrator/settings/csp-profiles",
        data=_create_form(),
        files={"certificate": ("client.txt", b"not-a-cert", "text/plain")},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "request_validation_error"


def test_create_rejects_missing_certificate_file():
    client = _client()
    client.app.dependency_overrides[create_profile_uc] = lambda: _ResultUseCase(
        _profile()
    )
    response = client.post(
        "/v1/policy-migrator/settings/csp-profiles",
        data=_create_form(),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "request_validation_error"


def test_patch_accepts_new_pem_file():
    client = _client()
    capture = _CapturingUseCase(_profile())
    client.app.dependency_overrides[update_profile_uc] = lambda: capture
    response = client.patch(
        f"/v1/policy-migrator/settings/csp-profiles/{uuid4()}",
        files=_pem_file(content=_PEM_SHORT),
    )

    assert response.status_code == 200
    assert capture.command is not None
    assert capture.command.certificate_bundle.data == _PEM_SHORT
    assert capture.command.certificate_bundle.format is CertificateBundleFormat.PEM
