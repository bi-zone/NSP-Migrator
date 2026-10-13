from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.fastapi.error_handlers import error_response
from app.modules.settings.csp_profiles.domain.exceptions import (
    CredentialDecryptionError,
    CredentialEncryptionError,
    CSPProfileAuthenticationError,
    CSPProfileConnectionError,
    CSPProfileConnectionValidationError,
    CSPProfileNotFoundError,
    CSPProfilePreconditionRequiredError,
    CSPProfileRequiredError,
    DuplicateCSPProfileNameError,
    InvalidCertificateBundleError,
    InvalidCSPProfileError,
)


def register_csp_profile_exception_handlers(app: FastAPI) -> None:
    async def handle_invalid_profile(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        return error_response(
            request,
            status_code=422,
            code="csp_profile_invalid",
            message="CSP profile input is invalid",
        )

    async def handle_profile_not_found(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        return error_response(
            request,
            status_code=404,
            code="csp_profile_not_found",
            message="CSP profile was not found",
        )

    async def handle_profile_conflict(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        return error_response(
            request,
            status_code=409,
            code="csp_profile_conflict",
            message="CSP profile conflicts with current state",
        )

    async def handle_profile_required(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        return error_response(
            request,
            status_code=409,
            code="csp_profile_required",
            message="A stored CSP profile is required",
        )

    async def handle_precondition_required(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        return error_response(
            request,
            status_code=428,
            code="precondition_required",
            message="If-Match header is required",
        )

    async def handle_connection_rejected(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        return error_response(
            request,
            status_code=422,
            code="csp_connection_rejected",
            message="CSP connection settings were rejected",
        )

    async def handle_connection_failed(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        return error_response(
            request,
            status_code=502,
            code="csp_connection_failed",
            message="CSP connection test failed",
        )

    async def handle_credential_store_unavailable(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        return error_response(
            request,
            status_code=503,
            code="credential_store_unavailable",
            message="Credential store is unavailable",
        )

    app.add_exception_handler(
        InvalidCSPProfileError,
        handle_invalid_profile,
    )
    app.add_exception_handler(
        InvalidCertificateBundleError,
        handle_invalid_profile,
    )
    app.add_exception_handler(
        CSPProfileNotFoundError,
        handle_profile_not_found,
    )
    app.add_exception_handler(
        DuplicateCSPProfileNameError,
        handle_profile_conflict,
    )
    app.add_exception_handler(
        CSPProfileRequiredError,
        handle_profile_required,
    )
    app.add_exception_handler(
        CSPProfilePreconditionRequiredError,
        handle_precondition_required,
    )
    app.add_exception_handler(
        CSPProfileConnectionValidationError,
        handle_connection_rejected,
    )
    app.add_exception_handler(
        CSPProfileAuthenticationError,
        handle_connection_rejected,
    )
    app.add_exception_handler(
        CSPProfileConnectionError,
        handle_connection_failed,
    )
    app.add_exception_handler(
        CredentialEncryptionError,
        handle_credential_store_unavailable,
    )
    app.add_exception_handler(
        CredentialDecryptionError,
        handle_credential_store_unavailable,
    )
