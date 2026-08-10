from pydantic import BaseModel, Field, computed_field


class ServerConfig(BaseModel):
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)
    name: str = Field(default="policy-migrator-back-project")
    version: str = Field(default="0.1.0")
    env: str = Field(default="local")
    api_version: str = Field(default="v1")
    api_slug: str = Field(default="policy-migrator")
    public_base_url: str = Field(default="http://localhost:8000")
    contact_name: str = Field(default="Team Policy Migrator")
    contact_email: str = Field(default="policy-migrator@example.com")

    @computed_field
    @property
    def docs_url(self) -> str:
        return f"/{self.api_version}/{self.api_slug}/docs"

    @computed_field
    @property
    def redoc_url(self) -> str:
        return f"/{self.api_version}/{self.api_slug}/redoc"

    @computed_field
    @property
    def openapi_url(self) -> str:
        return f"/{self.api_version}/{self.api_slug}/openapi.json"

    @computed_field
    @property
    def health_url(self) -> str:
        return "/health"
