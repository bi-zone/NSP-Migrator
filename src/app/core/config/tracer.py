from pydantic import BaseModel, Field


class TracerConfig(BaseModel):
    enabled: bool = Field(default=True)
    header_name: str = Field(default="X-Request-ID")
