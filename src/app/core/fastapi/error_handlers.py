import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.errors import (
    AppError,
    ConflictError,
    DomainValidationError,
    InfrastructureError,
    NotFoundError,
)

logger = logging.getLogger(__name__)
ExceptionHandler = Callable[
    [Request, Exception], JSONResponse | Awaitable[JSONResponse]
]


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", "-")
    return str(value)


def _error_payload(
    *, code: str, message: str, request_id: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": request_id,
    }
    if details:
        payload["details"] = details
    return payload


def _respond(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=_error_payload(
            code=code,
            message=message,
            request_id=_request_id(request),
            details=details,
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    def _register(exc_type: type[Exception], handler: ExceptionHandler) -> None:
        app.add_exception_handler(exc_type, handler)

    async def handle_domain_validation(
        request: Request, exc: Exception
    ) -> JSONResponse:
        return _respond(
            request,
            status_code=422,
            code="domain_validation_error",
            message=str(exc),
        )

    async def handle_not_found(request: Request, exc: Exception) -> JSONResponse:
        return _respond(
            request,
            status_code=404,
            code="not_found",
            message=str(exc),
        )

    async def handle_conflict(request: Request, exc: Exception) -> JSONResponse:
        return _respond(
            request,
            status_code=409,
            code="conflict",
            message=str(exc),
        )

    async def handle_integrity_error(request: Request, exc: Exception) -> JSONResponse:
        # TODO: сократить логгировавание после рефактора
        orig = getattr(exc, "orig", None)
        logger.warning(
            "integrity error",
            extra={
                "request_id": _request_id(request),
                "error": str(exc),
                "driver_error": str(orig) if orig is not None else None,
                "pgcode": getattr(orig, "sqlstate", None)
                or getattr(orig, "pgcode", None),
            },
        )
        return _respond(
            request,
            status_code=409,
            code="integrity_conflict",
            message="Database constraint conflict",
        )

    async def handle_infrastructure_error(
        request: Request, exc: Exception
    ) -> JSONResponse:
        return _respond(
            request,
            status_code=503,
            code="infrastructure_error",
            message=str(exc),
        )

    async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
        return _respond(
            request,
            status_code=400,
            code="app_error",
            message=str(exc),
        )

    async def handle_unhandled_exception(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception(
            "unhandled exception",
            extra={"request_id": _request_id(request)},
        )

        return _respond(
            request,
            status_code=500,
            code="internal_server_error",
            message=str(exc),
        )

    _register(DomainValidationError, handle_domain_validation)
    _register(NotFoundError, handle_not_found)
    _register(ConflictError, handle_conflict)
    _register(IntegrityError, handle_integrity_error)
    _register(InfrastructureError, handle_infrastructure_error)
    _register(AppError, handle_app_error)

    # fallback
    _register(Exception, handle_unhandled_exception)
