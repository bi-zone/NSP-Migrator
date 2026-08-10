from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field
from sqlalchemy.engine import URL


class DatabaseConfig(BaseModel):
    host: str = Field(default="localhost")
    port: int = Field(default=5432, ge=1, le=65535)
    user: str = Field(default="postgres")
    password: str = Field(default="postgres")
    name: str = Field(default="policy_migrator")
    driver_async: Literal["asyncpg"] = Field(default="asyncpg")
    driver_sync: Literal["psycopg"] = Field(default="psycopg")
    echo: bool = Field(default=False)
    pool_size: int = Field(default=5, ge=1)
    max_overflow: int = Field(default=10, ge=0)

    @computed_field
    @property
    def async_url(self) -> str:
        return URL.create(
            drivername=f"postgresql+{self.driver_async}",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.name,
        ).render_as_string(hide_password=False)

    @computed_field
    @property
    def sync_url(self) -> str:
        return URL.create(
            drivername=f"postgresql+{self.driver_sync}",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.name,
        ).render_as_string(hide_password=False)
