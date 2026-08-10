"""Top-level router assembly for imports HTTP endpoints.

The module keeps endpoint prefixes and tags centralized while delegating
resource handlers to dedicated router modules.
"""

from fastapi import APIRouter

from app.modules.imports.http.routers import (
    artifacts_router,
    sources_router,
    uploads_router,
    vendors_router,
)

imports_router = APIRouter(prefix="/imports", tags=["imports"])
imports_router.include_router(sources_router)
imports_router.include_router(vendors_router)
imports_router.include_router(uploads_router)
imports_router.include_router(artifacts_router)

__all__ = ["imports_router"]
