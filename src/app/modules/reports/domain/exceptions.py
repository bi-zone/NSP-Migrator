from app.core.errors import AppError, DomainValidationError, NotFoundError


class ReportsModuleError(AppError):
    """Base reports module error."""


class ReportsModuleDomainValidationError(DomainValidationError):
    """Raised when a report snapshot violates a domain invariant."""


class ReportsModuleNotFoundError(NotFoundError):
    """Raised when a requested report does not exist."""
