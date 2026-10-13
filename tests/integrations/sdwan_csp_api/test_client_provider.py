import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.infrastructure.interfaces.http_requester import HttpResponseStatusError
from app.integrations.sdwan_csp_api.client import SDWANCspHttpClient
from app.integrations.sdwan_csp_api.client_provider import SDWANClientProvider
from app.integrations.sdwan_csp_api.exceptions import SDWANCspHttpError
from app.integrations.sdwan_csp_api.interfaces import SDWANHttpMethod
from app.integrations.sdwan_csp_api.schemas import (
    AllowedVPCResponse,
    LoginResponse,
)
from app.modules.settings.csp_profiles.domain.entities import CSPProfile
from app.modules.settings.csp_profiles.domain.value_objects import (
    ProfileCredentials,
    StoredCredentialMetadata,
)


class _Profiles:
    def __init__(self, state):
        self.state = state

    async def get_by_id(self, profile_id):
        return self.state.get(profile_id)

    async def list_all(self):
        return list(self.state.values())


class _Credentials:
    def __init__(self, state):
        self.state = state

    async def get_for_connection(self, profile_id):
        return self.state.get(profile_id)


class _Uow:
    def __init__(self, profiles, credentials):
        self.profiles = _Profiles(profiles)
        self.credentials = _Credentials(credentials)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None


class _Client:
    def __init__(self, *, profile_id, vpc_id):
        self.profile_id = profile_id
        self.vpc_id = vpc_id
        self.close_calls = 0
        self.token = f"token-{profile_id}"

    async def login(self):
        return LoginResponse(
            token=self.token,
            allowed_vpcs=[
                AllowedVPCResponse(
                    vpc_id="vpc-1",
                    customer_name="Customer",
                    project_name="Project",
                    cuid="cuid",
                    pid="pid",
                )
            ],
        )

    async def aclose(self):
        self.close_calls += 1


class _Factory:
    def __init__(self):
        self.clients = []

    def create(self, *, profile, credentials, vpc_id):
        assert credentials.certificate_pem == "combined-pem"
        client = _Client(profile_id=profile.id, vpc_id=vpc_id)
        self.clients.append(client)
        return client


def _profile(*, name, target_revision=1):
    now = datetime.now(UTC)
    return CSPProfile(
        id=uuid4(),
        name=name,
        base_url=f"https://{name}.example",
        is_active=True,
        username=name,
        created_at=now,
        updated_at=now,
        credential_metadata=StoredCredentialMetadata(
            has_password=True,
            has_certificate=True,
            certificate_sha256="a" * 64,
            certificate_not_after=now + timedelta(days=1),
            certificate_has_private_key=True,
        ),
    )


def _provider(*profiles):
    profile_state = {profile.id: profile for profile in profiles}
    credential_state = {
        profile.id: ProfileCredentials(
            certificate_pem="combined-pem",
            password=f"password-{profile.name}",
        )
        for profile in profiles
    }
    factory = _Factory()
    provider = SDWANClientProvider(
        uow_factory=lambda: _Uow(profile_state, credential_state),
        client_factory=factory,
    )
    return provider, factory, profile_state


@pytest.mark.asyncio
async def test_discovery_parses_safe_allowed_vpc_fields_and_closes():
    profile = _profile(name="one")
    provider, factory, _ = _provider(profile)

    result = await provider.discover_vpcs(profile.id)

    assert result == [
        AllowedVPCResponse(
            vpc_id="vpc-1",
            customer_name="Customer",
            project_name="Project",
            cuid="cuid",
            pid="pid",
        )
    ]
    assert factory.clients[0].vpc_id is None
    assert factory.clients[0].close_calls == 1


@pytest.mark.asyncio
async def test_parallel_profiles_have_isolated_clients_tokens_and_vpcs():
    first = _profile(name="first")
    second = _profile(name="second")
    provider, factory, _ = _provider(first, second)
    seen = []

    async def use(profile, vpc):
        async with provider.acquire(profile.id, vpc) as client:
            await asyncio.sleep(0)
            seen.append((client.profile_id, client.vpc_id, client.token))

    await asyncio.gather(use(first, "vpc-a"), use(second, "vpc-b"))

    assert set(seen) == {
        (first.id, "vpc-a", f"token-{first.id}"),
        (second.id, "vpc-b", f"token-{second.id}"),
    }
    assert len({id(client) for client in factory.clients}) == 2
    assert all(client.close_calls == 1 for client in factory.clients)


@pytest.mark.asyncio
async def test_close_all_closes_inflight_once_and_finalizer_does_not_double_close():
    profile = _profile(name="one")
    provider, factory, _ = _provider(profile)

    async with provider.acquire(profile.id, "vpc-1"):
        await provider.close_all()
        assert factory.clients[0].close_calls == 1

    assert factory.clients[0].close_calls == 1


def test_login_response_parses_complete_allowed_vpcs_and_ignores_sensitive_user_data():
    response = LoginResponse.model_validate(
        {
            "token": "secret-token",
            "vpc_id": None,
            "allowed_vpcs": [
                {
                    "vpc_id": "vpc-1",
                    "customer_name": "Customer",
                    "project_name": "Project",
                    "cuid": "cuid",
                    "pid": "pid",
                    "permissions": ["admin"],
                },
                {
                    "vpc_id": "vpc-2",
                    "customer_name": "Second Customer",
                    "project_name": "Second Project",
                    "cuid": "second-cuid",
                    "pid": "second-pid",
                    "permissions": ["read", "write"],
                },
            ],
            "user": {"password": "must-not-escape"},
        }
    )

    assert [vpc.model_dump() for vpc in response.allowed_vpcs] == [
        {
            "vpc_id": "vpc-1",
            "customer_name": "Customer",
            "project_name": "Project",
            "cuid": "cuid",
            "pid": "pid",
        },
        {
            "vpc_id": "vpc-2",
            "customer_name": "Second Customer",
            "project_name": "Second Project",
            "cuid": "second-cuid",
            "pid": "second-pid",
        },
    ]
    assert not hasattr(response, "user")


def test_login_response_rejects_incomplete_allowed_vpc() -> None:
    with pytest.raises(ValidationError, match="project_name"):
        LoginResponse.model_validate(
            {
                "token": "secret-token",
                "allowed_vpcs": [
                    {
                        "vpc_id": "vpc-1",
                        "customer_name": "Customer",
                        "cuid": "cuid",
                        "pid": "pid",
                    }
                ],
            }
        )


@pytest.mark.asyncio
async def test_selected_vpc_is_used_for_login_before_target_loading():
    class _Requester:
        def __init__(self):
            self.calls = []

        async def request(self, method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            if url.endswith("/us/v1/login"):
                return {"token": "selected-token", "vpc_id": "vpc-2"}
            return {"result": []}

        async def aclose(self):
            return None

    requester = _Requester()
    client = SDWANCspHttpClient(
        base_url="https://example.test",
        username="user",
        password="password",
        vpc_id="vpc-2",
        requester=requester,
    )

    assert await client.get_device_objects() == []
    assert requester.calls[0][2]["json"]["vpc_id"] == "vpc-2"
    assert requester.calls[1][1].endswith("/ac/v1/device_objects")


@pytest.mark.skip("Is it need to hide error info?")
@pytest.mark.asyncio
async def test_client_error_never_contains_remote_response_body_secret():
    class _Requester:
        calls = 0

        async def request(self, *_, **__):
            self.calls += 1
            if self.calls == 1:
                return {"token": "token", "vpc_id": "vpc-1"}
            raise HttpResponseStatusError(
                status_code=500,
                response_body="PASSWORD-SECRET-MARKER",
            )

        async def aclose(self):
            return None

    client = SDWANCspHttpClient(
        base_url="https://example.test",
        username="user",
        password="password",
        vpc_id="vpc-1",
        requester=_Requester(),
    )

    with pytest.raises(SDWANCspHttpError) as raised:
        await client.authorized_request(method=SDWANHttpMethod.GET, path="/test")

    assert "PASSWORD-SECRET-MARKER" not in str(raised.value)


@pytest.mark.asyncio
async def test_cancelled_lease_closes_client():
    profile = _profile(name="one")
    provider, factory, _ = _provider(profile)
    entered = asyncio.Event()

    async def operation():
        async with provider.acquire(profile.id, "vpc-1"):
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(operation())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert factory.clients[0].close_calls == 1
