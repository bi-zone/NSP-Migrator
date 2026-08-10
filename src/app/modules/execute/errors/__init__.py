from app.core.errors import (
    AppError as BaseAppError,
)
from app.core.errors import (
    ConflictError as BaseConflictError,
)
from app.core.errors import (
    DomainValidationError as BaseDomainValidationError,
)
from app.core.errors import (
    InfrastructureError as BaseInfrastructureError,
)
from app.core.errors import (
    NotFoundError as BaseNotFoundError,
)


class ExecuteModuleError(BaseAppError):
    """Base mapping module error."""


class DomainValidationError(ExecuteModuleError, BaseDomainValidationError):
    """Raised when domain invariants are violated."""


class NotFoundError(ExecuteModuleError, BaseNotFoundError):
    """Raised when entity is not found."""


class ConflictError(ExecuteModuleError, BaseConflictError):
    """Raised when requested action conflicts with existing state."""


class InfrastructureError(ExecuteModuleError, BaseInfrastructureError):
    """Raised when infrastructure dependency fails."""
