from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config.database import DatabaseConfig
from app.core.config.integrations.sdwan_csp_api import (
    IntegrationsConfig,
    SDWANCspApiConfig,
)
from app.core.config.log import LogConfig
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

    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "postgres"
    db_password: str = "postgres"
    db_name: str = "policy_migrator"

    sdwan_csp_api_url: str = "https://csp.service"
    sdwan_csp_cert: str = "/app/client_cert.pem"
    sdwan_csp_username: str = "admin"
    sdwan_csp_password: str = "admin"
    sdwan_vpc_id: str = ""

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
    def log(self) -> LogConfig:
        return LogConfig(level=self.log_level)

    @computed_field
    @property
    def tracer(self) -> TracerConfig:
        return TracerConfig()

    @computed_field
    @property
    def integrations(self) -> IntegrationsConfig:
        return IntegrationsConfig(
            sdwan_csp_api=SDWANCspApiConfig(
                base_url=self.sdwan_csp_api_url,
                cert_path=self.sdwan_csp_cert,
                username=self.sdwan_csp_username,
                password=self.sdwan_csp_password,
                vpc_id=self.sdwan_vpc_id,
            ),
        )
