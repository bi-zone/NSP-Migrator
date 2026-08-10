import re
from typing import Any

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def normalize_name(value: str) -> str:
    """
    Normalize human-readable object names for fuzzy-ish exact matching.

    The goal is not complex fuzzy matching.
    The goal is stable comparison for common differences:
    - case;
    - spaces;
    - underscores;
    - hyphens;
    - dots.

    Examples:
        "WEB-SERVER_01" -> "web server 01"
        "web.server.01" -> "web server 01"
    """
    normalized = value.strip().casefold()
    normalized = _NORMALIZE_RE.sub(" ", normalized)
    normalized = " ".join(normalized.split())
    return normalized


def normalize_fqdn(value: str) -> str:
    """
    Normalize FQDN for value comparison.

    We intentionally keep this simple:
    - lower-case;
    - strip spaces;
    - remove trailing dot.
    """
    return value.strip().casefold().rstrip(".")


def normalize_protocol(value: str | None) -> str | None:
    """
    Normalize protocol string from canonical data.

    Returns lower-case stripped protocol or None.
    """
    if value is None:
        return None

    return value.strip().casefold()


def deduplicate_objects_by_id(items: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    result: list = []

    for item in items:
        if item.id in seen:
            continue

        seen.add(item.id)
        result.append(item)

    return result
