from functools import lru_cache

from app.core.config.app_settings import ApplicationSettings


@lru_cache(maxsize=1)
def get_settings() -> ApplicationSettings:
    return ApplicationSettings()


settings = get_settings()
