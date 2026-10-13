import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
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


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", "-")
    return str(value)


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    content: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": _request_id(request),
    }

    if details is not None:
        content["details"] = details

    return JSONResponse(status_code=status_code, content=content)


def register_exception_handlers(app: FastAPI) -> None:

    async def handle_domain_validation(
        request: Request, exc: Exception
    ) -> JSONResponse:
        return error_response(
            request,
            status_code=422,
            code="domain_validation_error",
            message=str(exc),
        )

    async def handle_not_found(request: Request, exc: Exception) -> JSONResponse:
        return error_response(
            request,
            status_code=404,
            code="not_found",
            message=str(exc),
        )

    async def handle_conflict(request: Request, exc: Exception) -> JSONResponse:
        return error_response(
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
        return error_response(
            request,
            status_code=409,
            code="integrity_conflict",
            message="Database constraint conflict",
        )

    async def handle_infrastructure_error(
        request: Request, exc: Exception
    ) -> JSONResponse:
        return error_response(
            request,
            status_code=503,
            code="infrastructure_error",
            message=str(exc),
        )

    async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
        return error_response(
            request,
            status_code=400,
            code="app_error",
            message=str(exc),
        )

    async def handle_unhandled_exception(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.error(
            "unhandled exception",
            extra={
                "request_id": _request_id(request),
                "exception_type": type(exc).__name__,
            },
        )

        return error_response(
            request,
            status_code=500,
            code="internal_server_error",
            message="Internal server error",
        )

    async def handle_request_validation(
        request: Request, exc: Exception
    ) -> JSONResponse:
        errors = exc.errors() if isinstance(exc, RequestValidationError) else []
        safe_errors = [
            {
                "type": error.get("type", "value_error"),
                "loc": list(error.get("loc", ())),
            }
            for error in errors
        ]
        return error_response(
            request,
            status_code=422,
            code="request_validation_error",
            message="Request validation failed",
            details={"errors": safe_errors},
        )

    app.add_exception_handler(RequestValidationError, handle_request_validation)
    app.add_exception_handler(DomainValidationError, handle_domain_validation)
    app.add_exception_handler(NotFoundError, handle_not_found)
    app.add_exception_handler(ConflictError, handle_conflict)
    app.add_exception_handler(IntegrityError, handle_integrity_error)
    app.add_exception_handler(InfrastructureError, handle_infrastructure_error)
    app.add_exception_handler(AppError, handle_app_error)

    # fallback
    app.add_exception_handler(Exception, handle_unhandled_exception)
