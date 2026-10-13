from time import sleep

from app.infrastructure.cache import InMemoryTTLStore


def test_store_returns_value_from_namespace() -> None:
    store = InMemoryTTLStore(ttl_seconds=1, max_entries=10)

    store.set("mapping", "scope-1", {"value": 1})

    assert store.get("mapping", "scope-1") == {"value": 1}


def test_store_isolates_namespaces() -> None:
    store = InMemoryTTLStore(ttl_seconds=1, max_entries=10)

    store.set("mapping", "same-key", "mapping-value")
    store.set("execute", "same-key", "execute-value")

    assert store.get("mapping", "same-key") == "mapping-value"
    assert store.get("execute", "same-key") == "execute-value"


def test_keys_returns_non_expired_namespace_keys_without_touching() -> None:
    store = InMemoryTTLStore(ttl_seconds=1, max_entries=10)
    store.set("mapping", "scope-1", "value")
    first_meta = store.get_meta("mapping", "scope-1")
    assert first_meta is not None

    sleep(0.01)

    assert store.keys("mapping") == ["scope-1"]
    meta_after_keys = store.get_meta("mapping", "scope-1")
    assert meta_after_keys is not None
    assert meta_after_keys.last_touched_at == first_meta.last_touched_at


def test_get_with_touch_extends_expiration() -> None:
    store = InMemoryTTLStore(ttl_seconds=1, max_entries=10)
    store.set("mapping", "scope-1", "value")
    first_meta = store.get_meta("mapping", "scope-1")
    assert first_meta is not None

    sleep(0.01)
    assert store.get("mapping", "scope-1", touch=True) == "value"
    touched_meta = store.get_meta("mapping", "scope-1")
    assert touched_meta is not None

    assert touched_meta.expires_at > first_meta.expires_at
    assert touched_meta.created_at == first_meta.created_at
    assert touched_meta.last_touched_at > first_meta.last_touched_at


def test_get_without_touch_keeps_expiration() -> None:
    store = InMemoryTTLStore(ttl_seconds=1, max_entries=10)
    store.set("mapping", "scope-1", "value")
    first_meta = store.get_meta("mapping", "scope-1")
    assert first_meta is not None

    sleep(0.01)
    assert store.get("mapping", "scope-1", touch=False) == "value"
    untouched_meta = store.get_meta("mapping", "scope-1")
    assert untouched_meta is not None

    assert untouched_meta.expires_at == first_meta.expires_at
    assert untouched_meta.last_touched_at == first_meta.last_touched_at


def test_store_expires_entries() -> None:
    store = InMemoryTTLStore(ttl_seconds=1, max_entries=10)
    store.set("mapping", "scope-1", "value")

    sleep(1.01)

    assert store.get("mapping", "scope-1") is None
    assert store.get_meta("mapping", "scope-1") is None


def test_store_removes_metadata_after_max_entries_eviction() -> None:
    store = InMemoryTTLStore(ttl_seconds=1, max_entries=1)
    store.set("mapping", "scope-1", "first")
    store.set("mapping", "scope-2", "second")

    assert store.get("mapping", "scope-1", touch=False) is None
    assert store.get_meta("mapping", "scope-1") is None
    assert store.get("mapping", "scope-2", touch=False) == "second"
    assert store.get_meta("mapping", "scope-2") is not None


def test_delete_removes_value_and_metadata() -> None:
    store = InMemoryTTLStore(ttl_seconds=1, max_entries=10)
    store.set("mapping", "scope-1", "value")

    store.delete("mapping", "scope-1")

    assert store.get("mapping", "scope-1") is None
    assert store.get_meta("mapping", "scope-1") is None
