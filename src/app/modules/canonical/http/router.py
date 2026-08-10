"""Top-level router assembly for canonical HTTP endpoints."""

from fastapi import APIRouter

from app.modules.canonical.http.routers import (
    issues_router,
    objects_router,
    rules_router,
    snapshots_router,
    zones_router,
)

canonical_router = APIRouter(prefix="/canonical", tags=["canonical"])
canonical_router.include_router(snapshots_router)
canonical_router.include_router(zones_router)
canonical_router.include_router(objects_router)
canonical_router.include_router(rules_router)
canonical_router.include_router(issues_router)

__all__ = ["canonical_router"]
