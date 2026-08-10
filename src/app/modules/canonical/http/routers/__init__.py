from app.modules.canonical.http.routers.issues import router as issues_router
from app.modules.canonical.http.routers.objects import router as objects_router
from app.modules.canonical.http.routers.rules import router as rules_router
from app.modules.canonical.http.routers.snapshots import router as snapshots_router
from app.modules.canonical.http.routers.zones import router as zones_router

__all__ = [
    "issues_router",
    "objects_router",
    "rules_router",
    "snapshots_router",
    "zones_router",
]
