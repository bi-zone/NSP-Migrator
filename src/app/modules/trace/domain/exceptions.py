from app.core.errors import AppError, DomainValidationError


class TraceModuleError(AppError):
    """Base trace module error."""


class TraceModuleValidationError(DomainValidationError):
    """Raised when trace query parameters violate module invariants."""
