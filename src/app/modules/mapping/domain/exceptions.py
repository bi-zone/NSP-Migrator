from app.core.errors import (
    AppError,
    ConflictError,
    DomainValidationError,
    InfrastructureError,
    NotFoundError,
)


class MappingModuleError(AppError):
    """Base mapping module error."""


class MappingModuleDomainValidationError(DomainValidationError):
    """Raised when domain invariants are violated."""


class MappingModuleNotFoundError(NotFoundError):
    """Raised when entity is not found."""


class MappingModuleConflictError(ConflictError):
    """Raised when requested action conflicts with existing state."""


class MappingModuleInfrastructureError(InfrastructureError):
    """Raised when infrastructure dependency fails."""
