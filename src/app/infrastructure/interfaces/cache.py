from collections.abc import Hashable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class CacheEntryMeta:
    created_at: datetime
    last_touched_at: datetime
    expires_at: datetime
    ttl_seconds: int

    def seconds_left(self, *, now: datetime) -> int:
        return max(0, int((self.expires_at - now).total_seconds()))


class RuntimeCacheStorePort(Protocol):
    def get(
        self,
        namespace: str,
        key: Hashable,
        *,
        touch: bool = True,
    ) -> Any | None: ...

    def set(self, namespace: str, key: Hashable, value: Any) -> None: ...

    def delete(self, namespace: str, key: Hashable) -> None: ...

    def touch(self, namespace: str, key: Hashable) -> bool: ...

    def get_meta(self, namespace: str, key: Hashable) -> CacheEntryMeta | None: ...

    def keys(self, namespace: str) -> list[Hashable]: ...
