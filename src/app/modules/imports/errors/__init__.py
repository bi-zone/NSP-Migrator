from app.core.errors import DomainValidationError as BaseDomainValidationError
from app.core.errors import NotFoundError as BaseNotFoundError


class ImportsModuleError(Exception):
    """Base error for imports module."""


class DomainValidationError(ImportsModuleError, BaseDomainValidationError):
    """Imports-specific domain validation error."""


class NotFoundError(ImportsModuleError, BaseNotFoundError):
    """Imports-specific not-found error."""


class SourceArtifactNotFoundError(NotFoundError):
    """Raised when source artifact is absent for given source snapshot."""
