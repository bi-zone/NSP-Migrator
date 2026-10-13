from app.core.errors import (
    AppError,
    ConflictError,
    DomainValidationError,
    InfrastructureError,
    NotFoundError,
)


class ExecuteModuleError(AppError):
    """Base mapping module error."""


class ExecuteModuleDomainValidationError(DomainValidationError):
    """Raised when domain invariants are violated."""


class ExecuteModuleNotFoundError(NotFoundError):
    """Raised when entity is not found."""


class ExecuteModuleConflictError(ConflictError):
    """Raised when requested action conflicts with existing state."""


class ExecuteModuleInfrastructureError(InfrastructureError):
    """Raised when infrastructure dependency fails."""
