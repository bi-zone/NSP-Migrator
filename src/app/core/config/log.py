from pydantic import BaseModel, Field


class LogConfig(BaseModel):
    level: str = Field(default="INFO")
    json_logs: bool = Field(default=True)
