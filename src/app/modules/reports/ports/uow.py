from typing import Protocol

from app.infrastructure.interfaces.db import IAsyncUnitOfWork
from app.modules.reports.ports.report_repository import ReportsRepositoryPort


class ReportsUnitOfWorkPort(IAsyncUnitOfWork, Protocol):
    """Transaction owner for the Report aggregate repository."""

    reports: ReportsRepositoryPort
