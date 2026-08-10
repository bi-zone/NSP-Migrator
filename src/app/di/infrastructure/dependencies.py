from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine

from app.di.dependencies import get_di_container
from app.di.infrastructure.container import InfrastructureContainer


def get_infrastructure_container(request: Request) -> InfrastructureContainer:
    return get_di_container(request).infrastructure()


def get_db_engine(
    infra_container: InfrastructureContainer = Depends(get_infrastructure_container),
) -> AsyncEngine:
    return infra_container.async_engine()
