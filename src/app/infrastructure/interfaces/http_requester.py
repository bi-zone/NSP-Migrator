from enum import StrEnum
from typing import Any, Protocol, TypeAlias

HttpRequesterJsonPrimitive: TypeAlias = str | int | float | bool | None
HttpRequesterJsonValue: TypeAlias = (
    HttpRequesterJsonPrimitive
    | dict[str, "HttpRequesterJsonValue"]
    | list["HttpRequesterJsonValue"]
)


class HttpMethod(StrEnum):
    GET = "GET"
    POST = "POST"


# -- Base Http Requester Exceptions
class HttpRequesterError(Exception):
    """Base exception for abstract HTTP requester."""


class HttpRequestTransportError(HttpRequesterError):
    """Network or transport-level error."""

    def __init__(self, message: str = "HTTP transport error") -> None:
        super().__init__(message)


class HttpRequestTimeoutError(HttpRequesterError):
    """Request timeout."""

    def __init__(self, message: str = "HTTP request timeout") -> None:
        super().__init__(message)


class HttpResponseStatusError(HttpRequesterError):
    """HTTP response returned non-success status code."""

    def __init__(
        self,
        status_code: int,
        message: str = "HTTP response returned error status",
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


# -- Http Requester Interface
class IAsyncHttpRequester(Protocol):
    async def request(
        self,
        method: HttpMethod,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json: HttpRequesterJsonValue | None = None,
    ) -> HttpRequesterJsonValue: ...
