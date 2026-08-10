from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import ApplicationSettings
from app.di.dependencies import get_app_settings
from app.di.infrastructure.dependencies import get_db_engine

router = APIRouter()


@router.get("/health")
async def healthcheck(
    app_settings: ApplicationSettings = Depends(get_app_settings),
) -> dict[str, str]:
    return {
        "status": "ok",
        "service": app_settings.server.name,
        "env": app_settings.server.env,
    }


@router.get("/ready")
async def readiness(db_engine: AsyncEngine = Depends(get_db_engine)) -> dict[str, str]:
    async with db_engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ready"}
