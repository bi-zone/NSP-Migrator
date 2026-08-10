from fastapi import Depends, Request

from app.core.config import ApplicationSettings
from app.di.container import AppContainer


def get_di_container(request: Request) -> AppContainer:
    return request.app.state.di_container


def get_app_settings(
    di_container: AppContainer = Depends(get_di_container),
) -> ApplicationSettings:
    return di_container.app_settings()
