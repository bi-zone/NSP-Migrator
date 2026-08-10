"""Use case for creating or reusing import sources."""

from __future__ import annotations

from dataclasses import dataclass

from app.infrastructure.db.transactional import async_transactional
from app.modules.imports.application.dto import ImportSourceDTO
from app.modules.imports.domain.import_source import ImportSource
from app.modules.imports.errors import DomainValidationError
from app.modules.imports.ports.uow import ImportsUoWPort


@dataclass(slots=True)
class CreateImportSourceCommand:
    """Input command for source creation flow."""
    vendor_code: str
    name: str
    description: str | None = None
    active: bool = True


@dataclass(slots=True)
class CreateImportSourceResult:
    """Represent output payload returned by CreateImportSource flow."""
    source: ImportSourceDTO
    created: bool


class CreateImportSourceUseCase:
    """Create import source with vendor validation and idempotent semantics."""
    def __init__(self, uow: ImportsUoWPort) -> None:
        self.uow = uow

    @async_transactional()
    async def execute(
        self, command: CreateImportSourceCommand
    ) -> CreateImportSourceResult:
        """Validate vendor and create source or return existing one.

        Args:
            command: Source creation payload from HTTP/application boundary.

        Returns:
            Result containing source projection and created marker.

        Raises:
            DomainValidationError: When vendor does not exist or is inactive.
        """
        vendor = await self.uow.vendors.get_by_code(command.vendor_code)
        if vendor is None or not vendor.active:
            raise DomainValidationError(
                f"Unknown or inactive vendor_code: {command.vendor_code}"
            )

        existing = await self.uow.sources.get_by_vendor_code_and_name(
            command.vendor_code, command.name
        )
        if existing:
            return CreateImportSourceResult(
                source=ImportSourceDTO(
                    id=existing.id,
                    vendor_code=existing.vendor_code,
                    name=existing.name,
                    description=existing.description,
                    active=existing.active,
                    created_at=existing.created_at,
                    updated_at=existing.updated_at,
                ),
                created=False,
            )

        source = ImportSource.create(
            vendor_code=command.vendor_code,
            name=command.name,
            description=command.description,
            active=command.active,
        )
        await self.uow.sources.save(source)
        return CreateImportSourceResult(
            source=ImportSourceDTO(
                id=source.id,
                vendor_code=source.vendor_code,
                name=source.name,
                description=source.description,
                active=source.active,
                created_at=source.created_at,
                updated_at=source.updated_at,
            ),
            created=True,
        )
