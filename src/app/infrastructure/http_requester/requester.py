import ssl
from typing import Any

import httpx

from app.infrastructure.interfaces.http_requester import (
    HttpMethod,
    HttpRequesterJsonValue,
    HttpRequestTimeoutError,
    HttpRequestTransportError,
    HttpResponseStatusError,
    IAsyncHttpRequester,
)


class HttpxRequester(IAsyncHttpRequester):
    def __init__(
        self,
        *,
        verify_server_ssl: bool | ssl.SSLContext = True,
        cert_path: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._client = httpx.AsyncClient(
            verify=verify_server_ssl,
            cert=cert_path,
            timeout=httpx.Timeout(timeout),
        )

    async def request(
        self,
        method: HttpMethod,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json: HttpRequesterJsonValue | None = None,
    ) -> HttpRequesterJsonValue:
        try:
            response = await self._client.request(
                method=method,
                url=url,
                params=params,
                headers=headers,
                json=json,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise HttpRequestTimeoutError() from exc
        except httpx.HTTPStatusError as exc:
            body: str | None
            try:
                body = exc.response.text
            except Exception:
                body = None

            raise HttpResponseStatusError(
                status_code=exc.response.status_code,
                message=f"HTTP request failed with status {exc.response.status_code}",
                response_body=body,
            ) from exc
        except httpx.RequestError as exc:
            raise HttpRequestTransportError() from exc

        return response.json()
