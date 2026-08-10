"""Domain exceptions for canonical module not-found paths.

CanonicalModuleNotFoundError subclasses core NotFoundError, so FastAPI
maps it to HTTP 404 via app.core.fastapi.error_handlers.
"""

from app.core.errors import AppError, NotFoundError


class CanonicalModuleError(AppError):
    """Base canonical module error."""


class CanonicalModuleNotFoundError(NotFoundError):
    """Raised when a canonical entity is not found."""
