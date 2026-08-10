"""Resource routers for the imports HTTP API."""

from app.modules.imports.http.routers.artifacts import router as artifacts_router
from app.modules.imports.http.routers.sources import router as sources_router
from app.modules.imports.http.routers.uploads import router as uploads_router
from app.modules.imports.http.routers.vendors import router as vendors_router

__all__ = [
    "artifacts_router",
    "sources_router",
    "uploads_router",
    "vendors_router",
]
