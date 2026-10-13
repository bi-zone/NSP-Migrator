from typing import Self

from pydantic import Field, SecretStr, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config.csp_credentials import CSPCredentialsConfig
from app.core.config.database import DatabaseConfig
from app.core.config.log import LogConfig
from app.core.config.runtime_cache import RuntimeCacheConfig
from app.core.config.server import ServerConfig
from app.core.config.tracer import TracerConfig


class ApplicationSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    name: str = "ratel-policy-migrator"
    version: str = "0.1.0"
    env: str = "local"
    host: str = "0.0.0.0"
    port: int = 8000
    api_version: str = "v1"
    api_slug: str = "policy-migrator"
    public_base_url: str = "http://localhost:8000"
    contact_name: str = "Team RATEL"
    contact_email: str = "ratel@example.com"
    log_level: str = "INFO"
    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10
    runtime_cache_ttl_hours: int = Field(default=24, gt=0)
    runtime_cache_max_entries: int = Field(default=10_000, gt=0)

    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "postgres"
    db_password: str = "postgres"
    db_name: str = "policy_migrator"

    csp_master_key: SecretStr = Field(
        default_factory=lambda: _missing_csp_setting("APP_CSP_MASTER_KEY")
    )

    @model_validator(mode="after")
    def validate_csp_credentials(self) -> Self:
        CSPCredentialsConfig.from_settings(
            active_key=self.csp_master_key,
        )
        return self

    @computed_field  # Required for DI correct config parsing!
    @property
    def server(self) -> ServerConfig:
        return ServerConfig(
            host=self.host,
            port=self.port,
            name=self.name,
            version=self.version,
            env=self.env,
            api_version=self.api_version,
            api_slug=self.api_slug,
            public_base_url=self.public_base_url,
            contact_name=self.contact_name,
            contact_email=self.contact_email,
        )

    @computed_field
    @property
    def database(self) -> DatabaseConfig:
        return DatabaseConfig(
            host=self.db_host,
            port=self.db_port,
            user=self.db_user,
            password=self.db_password,
            name=self.db_name,
            echo=self.db_echo,
            pool_size=self.db_pool_size,
            max_overflow=self.db_max_overflow,
        )

    @computed_field
    @property
    def runtime_cache(self) -> RuntimeCacheConfig:
        return RuntimeCacheConfig(
            ttl_hours=self.runtime_cache_ttl_hours,
            max_entries=self.runtime_cache_max_entries,
        )

    @computed_field
    @property
    def log(self) -> LogConfig:
        return LogConfig(level=self.log_level)

    @computed_field
    @property
    def tracer(self) -> TracerConfig:
        return TracerConfig()

    @computed_field
    @property
    def csp_credentials(self) -> CSPCredentialsConfig:
        return CSPCredentialsConfig.from_settings(
            active_key=self.csp_master_key,
        )


def _missing_csp_setting(name: str):
    raise ValueError(f"Required CSP credential setting is missing: {name}")
