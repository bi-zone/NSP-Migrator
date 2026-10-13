"""Fixtures for the first backend migration workflow acceptance test."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from dependency_injector import providers

from app.di.container import AppContainer
from app.infrastructure.cache import InMemoryTTLStore
from app.infrastructure.db.session_factory import SQLAlchemySessionFactory
from tests.modules.end_to_end.flow_1.fake_sdwan import (
    FakeSDWANClientFactory,
    FakeSDWANState,
)


@pytest.fixture
def combined_client_pem() -> str:
    """Generate a valid, ephemeral certificate bundle for profile creation."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "flow-1-integration-client")]
    )
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return (
        certificate.public_bytes(serialization.Encoding.PEM)
        + key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    ).decode()


@pytest.fixture
def sdwan_state() -> FakeSDWANState:
    """Return isolated mutable SD-WAN data for one workflow invocation."""
    return FakeSDWANState()


@pytest.fixture
def backend_container(
    fresh_migrated_test_database,
    session_factory: SQLAlchemySessionFactory,
    sdwan_state: FakeSDWANState,
) -> Iterator[AppContainer]:
    """Compose real backend modules and replace only the external client seam."""
    container = AppContainer()
    fake_factory = FakeSDWANClientFactory(sdwan_state)
    container.infrastructure.session_factory.override(providers.Object(session_factory))
    container.infrastructure.runtime_cache_store.override(
        providers.Object(InMemoryTTLStore(ttl_seconds=60, max_entries=100))
    )
    container.settings_module().csp_profiles().sdwan_client_factory.override(
        providers.Object(fake_factory)
    )
    container.integrations().client_factory.override(providers.Object(fake_factory))
    try:
        yield container
    finally:
        container.unwire()
