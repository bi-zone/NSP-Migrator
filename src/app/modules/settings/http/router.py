from fastapi import APIRouter

from app.modules.settings.csp_profiles.http.router import router as csp_profiles_router

settings_router = APIRouter(prefix="/settings", tags=["settings"])
settings_router.include_router(csp_profiles_router)

__all__ = ["settings_router"]
