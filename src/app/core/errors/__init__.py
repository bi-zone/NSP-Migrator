class AppError(Exception):
    """Base application error."""


class DomainValidationError(AppError):
    """Raised when domain invariants are violated."""


class NotFoundError(AppError):
    """Raised when entity is not found."""


class ConflictError(AppError):
    """Raised when requested action conflicts with existing state."""


class InfrastructureError(AppError):
    """Raised when infrastructure dependency fails."""
