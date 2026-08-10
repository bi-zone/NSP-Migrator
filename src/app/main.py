from fastapi import FastAPI

from app.core.bootstrap import create_application
from app.http.router import build_api_router

app: FastAPI = create_application(build_api_router())


def run() -> None:
    """Poetry script entrypoint."""
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
