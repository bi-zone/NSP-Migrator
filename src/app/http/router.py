from fastapi import APIRouter

from app.core.config import settings
from app.http.health import router as health_router
from app.modules.canonical.http.router import canonical_router
from app.modules.execute.http.router import execute_router
from app.modules.imports.cisco_asa.http.router import cisco_asa_router
from app.modules.imports.http.router import imports_router
from app.modules.mapping.http.router import mapping_router
from app.modules.trace.http.router import trace_router


def build_api_router() -> APIRouter:
    api_router = APIRouter()

    versioned_router = APIRouter(
        prefix=f"/{settings.server.api_version}/{settings.server.api_slug}"
    )
    versioned_router.include_router(canonical_router)
    versioned_router.include_router(imports_router)
    versioned_router.include_router(cisco_asa_router)
    versioned_router.include_router(mapping_router)
    versioned_router.include_router(execute_router)
    versioned_router.include_router(trace_router)

    api_router.include_router(health_router)
    api_router.include_router(versioned_router)

    return api_router
