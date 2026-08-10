from collections.abc import Iterable, Mapping
from typing import Any, TypeVar
from uuid import UUID

import pandas as pd

T = TypeVar("T")


def build_map_by_field(  # noqa
    items: Iterable[T],
    field_name: str,  # id field as common case
) -> dict[Any, T]:
    """Builds hash map by a field for DTO/dataclass objects and dicts."""

    def get_field_value(item: T) -> Any:
        if isinstance(item, Mapping):
            return item[field_name]

        return getattr(item, field_name)

    return {get_field_value(item): item for item in items}


def normalize_key_map(raw_map: dict[Any, T]) -> dict[str, T]:  # noqa
    return {str_id(key): value for key, value in raw_map.items()}


def as_uuid(value: Any) -> UUID:
    raw_value = _unwrap(value)
    if isinstance(raw_value, UUID):
        return raw_value
    return UUID(str(raw_value))


def str_id(value: Any) -> str:
    raw_value = _unwrap(value)
    if raw_value is None:
        return ""
    return str(raw_value)


def short_id(value: Any) -> str:
    return str_id(value).split("-")[0]


def text(value: Any) -> str:
    raw_value = _unwrap(value)
    if raw_value is None or raw_value == "":
        return "—"
    return str(raw_value)


def _unwrap(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    return value


def to_jsonable(value: Any) -> Any:
    raw_value = _unwrap(value)

    if isinstance(raw_value, UUID):
        return str(raw_value)

    if isinstance(raw_value, list):
        return [to_jsonable(item) for item in raw_value]

    if isinstance(raw_value, tuple):
        return [to_jsonable(item) for item in raw_value]

    if isinstance(raw_value, set):
        return [to_jsonable(item) for item in raw_value]

    if isinstance(raw_value, dict):
        return {str(key): to_jsonable(val) for key, val in raw_value.items()}

    return raw_value


def _filter_df_rows_by_search(
    df: pd.DataFrame,
    search_query: str | None,
    search_columns: list[str],
) -> pd.DataFrame:
    """
    Filter dataframe rows by free-text search across multiple columns.

    Search is:
    - case-insensitive;
    - token-based (query is split by whitespace);
    - AND-based (every token must be present);
    - performed against a virtual text built by concatenating all
      values from `search_columns` for each row.

    Example:
        search_columns = ["name", "value"]

        Row:
            name="web-service"
            value="tcp/443"

        Search queries:
            "web"      -> match
            "443"      -> match
            "web 443"  -> match
            "web 53"   -> no match

    Args:
        df: Source dataframe.
        search_query: User search input.
        search_columns: Columns whose values participate in search.

    Returns:
        Dataframe containing only matched rows.
    """

    # Empty search means "show all rows".
    if not search_query or not search_query.strip():
        return df

    # Split query into individual search tokens.
    tokens: list[str] = search_query.lower().split()

    # Build a searchable text representation for every dataframe row
    # by concatenating values from all configured columns.
    searchable_text: pd.Series = (
        df[search_columns].fillna("").astype(str).agg(" ".join, axis=1).str.lower()
    )

    # Start with all rows matched.
    mask = pd.Series(True, index=df.index)

    # Keep only rows that contain every search token.
    for token in tokens:
        token_matches = searchable_text.str.contains(
            token,
            regex=False,
            na=False,
        )
        mask = mask & token_matches

    # return df part, that corresponds to the mask projection
    return df[mask]
