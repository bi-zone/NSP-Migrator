from app.integrations.sdwan_csp_api.client_factory import SDWANClientFactory
from app.integrations.sdwan_csp_api.exceptions import SDWANCspHttpAuthError
from app.modules.settings.csp_profiles.domain.entities import CSPProfile
from app.modules.settings.csp_profiles.domain.exceptions import (
    CSPProfileAuthenticationError,
    CSPProfileConnectionError,
)
from app.modules.settings.csp_profiles.domain.value_objects import ProfileCredentials
from app.modules.settings.csp_profiles.ports.connection_tester import (
    AllowedVPC,
    CSPProfileConnectionTesterPort,
)


class HttpxCSPProfileConnectionTester(CSPProfileConnectionTesterPort):
    """Perform one isolated login without using global CSP configuration."""

    def __init__(self, client_factory: SDWANClientFactory) -> None:
        self._client_factory = client_factory

    async def test(
        self,
        profile: CSPProfile,
        credentials: ProfileCredentials,
    ) -> list[AllowedVPC]:
        client = self._client_factory.create(
            profile=profile,
            credentials=credentials,
            vpc_id=None,
        )
        try:
            response = await client.login()
        except SDWANCspHttpAuthError:
            raise CSPProfileAuthenticationError from None
        except Exception:
            raise CSPProfileConnectionError from None
        finally:
            await client.aclose()

        return [
            AllowedVPC(
                vpc_id=item.vpc_id,
                customer_name=item.customer_name,
                project_name=item.project_name,
                cuid=item.cuid,
                pid=item.pid,
            )
            for item in response.allowed_vpcs
        ]
