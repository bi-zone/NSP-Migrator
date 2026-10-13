from streamlit_app.components.canonical.rule_selection import (
    dataframe_selection_state,
    merge_visible_page_selection,
    row_indices_for_selected_ids,
    selected_ids_from_row_indices,
    should_commit_widget_selection,
    visible_rows_token,
)

AAB = "aab-rule-id"
CCD = "ccd-rule-id"
EEF = "eef-rule-id"
PAGE_1 = [AAB, CCD, EEF]
PAGE_2 = ["rule-x", "rule-y", "rule-z"]


def test_row_indices_follow_rule_id_not_position() -> None:
    selected = {AAB}
    assert row_indices_for_selected_ids(PAGE_1, selected) == [0]
    assert row_indices_for_selected_ids([CCD, AAB, EEF], selected) == [1]
    assert row_indices_for_selected_ids(PAGE_2, selected) == []


def test_merge_keeps_hidden_ids_when_page_or_filter_changes() -> None:
    selected = {AAB, CCD}
    after_page_2 = merge_visible_page_selection(selected, PAGE_2, set())
    assert after_page_2 == {AAB, CCD}

    after_filter_without_aab = merge_visible_page_selection(
        selected, [CCD, EEF], {CCD}
    )
    assert after_filter_without_aab == {AAB, CCD}


def test_merge_drops_deselected_visible_id() -> None:
    selected = {AAB, CCD}
    after_deselect = merge_visible_page_selection(selected, PAGE_1, {AAB})
    assert after_deselect == {AAB}


def test_stale_positional_indices_do_not_select_new_rows() -> None:
    selected = {AAB}
    visible_after_filter = [EEF, CCD, "other"]
    restored_indices = row_indices_for_selected_ids(visible_after_filter, selected)
    assert restored_indices == []
    assert dataframe_selection_state(restored_indices)["selection"]["rows"] == []
    assert selected_ids_from_row_indices(visible_after_filter, [0, 2]) == {
        EEF,
        "other",
    }


def test_returning_to_page_restores_original_rule() -> None:
    selected = {AAB}
    assert row_indices_for_selected_ids(PAGE_1, selected) == [0]
    assert row_indices_for_selected_ids(PAGE_2, selected) == []
    assert row_indices_for_selected_ids(PAGE_1, selected) == [0]


def test_page_change_does_not_commit_stale_row_indices() -> None:
    selected = {AAB, CCD}
    page_2_expected = row_indices_for_selected_ids(PAGE_2, selected)
    assert page_2_expected == []
    assert not should_commit_widget_selection(data_changed=True, pending_sync=False)
    assert not should_commit_widget_selection(data_changed=False, pending_sync=True)
    assert should_commit_widget_selection(data_changed=False, pending_sync=False)

    stale_commit = merge_visible_page_selection(
        selected, PAGE_2, selected_ids_from_row_indices(PAGE_2, [0, 1, 2, 3])
    )
    assert stale_commit != selected
    skipped_commit = selected
    assert skipped_commit == {AAB, CCD}


def test_visible_rows_token_changes_when_page_ids_change() -> None:
    assert visible_rows_token(PAGE_1) != visible_rows_token(PAGE_2)
    assert visible_rows_token(PAGE_1) == visible_rows_token(list(PAGE_1))
