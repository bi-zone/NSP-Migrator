"""Map Streamlit dataframe row indices to stable canonical rule UUIDs."""

import hashlib


def row_indices_for_selected_ids(
    page_rule_ids: list[str],
    selected_ids: set[str],
) -> list[int]:
    """Map selected rule UUIDs onto row numbers of the currently visible page."""
    return [
        index
        for index, rule_id in enumerate(page_rule_ids)
        if rule_id in selected_ids
    ]


def dataframe_selection_state(row_indices: list[int]) -> dict:
    return {
        "selection": {
            "rows": row_indices,
            "columns": [],
            "cells": [],
        }
    }


def selected_ids_from_row_indices(
    page_rule_ids: list[str],
    row_indices: list[int] | tuple[int, ...] | None,
) -> set[str]:
    selected: set[str] = set()
    if not row_indices:
        return selected
    page_size = len(page_rule_ids)
    for row_index in row_indices:
        if 0 <= row_index < page_size:
            selected.add(page_rule_ids[row_index])
    return selected


def merge_visible_page_selection(
    selected_ids: set[str],
    page_rule_ids: list[str],
    selected_now: set[str],
) -> set[str]:
    """Replace this page's selection, keep IDs from other pages / hidden filters."""
    return (selected_ids - set(page_rule_ids)) | selected_now


def visible_rows_token(page_rule_ids: list[str]) -> str:
    digest = hashlib.sha256("\0".join(page_rule_ids).encode("utf-8")).hexdigest()
    return digest[:16]


def normalized_row_indices(
    row_indices: list[int] | tuple[int, ...] | None,
) -> list[int]:
    if not row_indices:
        return []
    return [int(index) for index in row_indices]


def selection_rows_match(expected: list[int], actual: list[int]) -> bool:
    return sorted(expected) == sorted(actual)


def should_commit_widget_selection(*, data_changed: bool, pending_sync: bool) -> bool:
    """Widget indices update UUID set only after the visible rows are stable."""
    return not data_changed and not pending_sync
