import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import ORJSONResponse

from app.core.config import settings
from app.core.fastapi.error_handlers import register_exception_handlers
from app.core.fastapi.metrics import register_metrics
from app.core.fastapi.tracer import RequestIdMiddleware
from app.core.logging import configure_logging
from app.di.container import create_di_container

logger = logging.getLogger(__name__)


def _resolve_static_directory() -> Path:
    candidate = Path(__file__).resolve().parents[1] / "modules/ui/http/static"
    if candidate.is_dir():
        return candidate
    raise RuntimeError(f"Static directory was not found: {candidate}")


def create_application(router: APIRouter) -> FastAPI:
    configure_logging()
    di_container = create_di_container()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info(
            "application started",
            extra={
                "request_id": "-",
                "service_name": settings.server.name,
                "service_env": settings.server.env,
                "health_url": f"{settings.server.public_base_url}{settings.server.health_url}",
                "docs_url": f"{settings.server.public_base_url}{settings.server.docs_url}",
                "redoc_url": f"{settings.server.public_base_url}{settings.server.redoc_url}",
                "openapi_url": f"{settings.server.public_base_url}{settings.server.openapi_url}",
                "db_migrations": "alembic",
            },
        )
        yield

    app = FastAPI(
        title=settings.server.name,
        version=settings.server.version,
        description="REST API and backend services",
        docs_url=settings.server.docs_url,
        redoc_url=settings.server.redoc_url,
        openapi_url=settings.server.openapi_url,
        default_response_class=ORJSONResponse,
        contact={
            "name": settings.server.contact_name,
            "email": settings.server.contact_email,
        },
        lifespan=lifespan,
        servers=[],
    )
    app.state.di_container = di_container
    app.add_middleware(RequestIdMiddleware, header_name=settings.tracer.header_name)
    register_metrics(app)
    register_exception_handlers(app)
    app.include_router(router)

    return app
