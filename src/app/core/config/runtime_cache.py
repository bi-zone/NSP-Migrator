from pydantic import BaseModel, Field, computed_field


class RuntimeCacheConfig(BaseModel):
    ttl_hours: int = Field(default=24, gt=0)
    max_entries: int = Field(default=10_000, gt=0)

    @computed_field
    @property
    def ttl_seconds(self) -> int:
        return self.ttl_hours * 60 * 60
