from __future__ import annotations


class DeterministicRuleKeyBuilder:
    """Generate stable rule keys and deterministic duplicate suffixes."""

    def __init__(self) -> None:
        self._seen: dict[str, int] = {}

    def build(self, base_key: str) -> str:
        count = self._seen.get(base_key, 0)
        self._seen[base_key] = count + 1
        if count == 0:
            return base_key
        return f"{base_key}:dup{count}"
