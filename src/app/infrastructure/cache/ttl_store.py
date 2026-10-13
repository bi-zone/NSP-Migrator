# mypy: ignore-errors
from collections.abc import Hashable
from dataclasses import dataclass
from datetime import timedelta
from threading import RLock
from typing import Any

from cachetools import TTLCache

from app.infrastructure.interfaces.cache import CacheEntryMeta, RuntimeCacheStorePort
from app.modules.common.domain.utils import get_utc_now


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    data: Any
    meta: CacheEntryMeta


TTLCacheEntries = TTLCache[Hashable, _CacheEntry, float]


class InMemoryTTLStore(RuntimeCacheStorePort):
    """
    Thread-safe in-process TTL store split by namespaces.

    Each namespace owns an independent ``TTLCache`` with the same TTL and size
    limit. Keys can repeat across namespaces without collisions, so module
    adapters can keep separate logical datasets over one shared store.

    User values are wrapped into an internal entry that stores data and TTL
    metadata together. Expiration and max-size eviction are delegated to
    ``TTLCache`` for the whole entry, without a separate metadata index.

    Methods are synchronous because ``cachetools`` is an in-memory synchronous
    collection. Operations are short and protected by an ``RLock`` so the same
    singleton can be shared across FastAPI and Streamlit threads.
    """

    def __init__(self, *, ttl_seconds: int, max_entries: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("Runtime cache ttl_seconds must be positive")
        if max_entries <= 0:
            raise ValueError("Runtime cache max_entries must be positive")

        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._caches: dict[str, TTLCacheEntries] = {}
        self._lock = RLock()

    def get(
        self,
        namespace: str,
        key: Hashable,
        *,
        touch: bool = True,
    ) -> Any | None:
        """
        Return cached data by namespace/key.

        Missing or expired entries are returned as ``None``. When ``touch`` is
        true, reading also extends the entry lifetime by rewriting the same data
        with fresh metadata.
        """
        with self._lock:
            cache = self._get_cache(namespace)
            entry: _CacheEntry | None = cache.get(key)
            if entry is None:
                return None

            if touch:
                entry = self._build_entry(data=entry.data, previous_meta=entry.meta)
                cache[key] = entry

            return entry.data

    def set(self, namespace: str, key: Hashable, value: Any) -> None:
        """Store data in a namespace and start or restart its TTL."""
        with self._lock:
            cache = self._get_cache(namespace)
            previous_entry = cache.get(key)
            cache[key] = self._build_entry(
                data=value,
                previous_meta=previous_entry.meta if previous_entry else None,
            )

    def delete(self, namespace: str, key: Hashable) -> None:
        """Remove data from a namespace if it exists."""
        with self._lock:
            self._get_cache(namespace).pop(key, None)

    def touch(self, namespace: str, key: Hashable) -> bool:
        """
        Extend entry lifetime without returning its data.

        Returns ``False`` for missing or expired entries.
        """
        with self._lock:
            cache = self._get_cache(namespace)
            entry = cache.get(key)
            if entry is None:
                return False

            cache[key] = self._build_entry(data=entry.data, previous_meta=entry.meta)
            return True

    def get_meta(self, namespace: str, key: Hashable) -> CacheEntryMeta | None:
        """Return TTL metadata for a namespace/key without extending lifetime."""
        with self._lock:
            entry = self._get_cache(namespace).get(key)
            return entry.meta if entry else None

    def keys(self, namespace: str) -> list[Hashable]:
        """
        Return current non-expired keys for a namespace.

        Listing keys does not touch entries and therefore does not extend their
        lifetime. Callers that operate on a concrete key can touch/read it
        explicitly afterwards.
        """
        with self._lock:
            return list(self._get_cache(namespace).keys())

    def _get_cache(self, namespace: str) -> TTLCacheEntries:
        """Return namespace cache, expiring stale entries before use."""
        if namespace not in self._caches:
            self._caches[namespace] = TTLCache(
                maxsize=self._max_entries,
                ttl=self._ttl_seconds,
            )
        cache = self._caches[namespace]
        cache.expire()
        return cache

    def _build_entry(
        self,
        *,
        data: Any,
        previous_meta: CacheEntryMeta | None,
    ) -> _CacheEntry:
        now = get_utc_now()
        created_at = previous_meta.created_at if previous_meta else now

        return _CacheEntry(
            data=data,
            meta=CacheEntryMeta(
                created_at=created_at,
                last_touched_at=now,
                expires_at=now + timedelta(seconds=self._ttl_seconds),
                ttl_seconds=self._ttl_seconds,
            ),
        )
