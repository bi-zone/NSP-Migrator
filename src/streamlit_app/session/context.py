from dataclasses import asdict, dataclass
from uuid import UUID

import streamlit as st


@dataclass
class SessionContext:
    source_id: UUID | None = None
    source_name: str | None = None
    vendor_code: str | None = None
    upload_id: UUID | None = None
    snapshot_id: UUID | None = None
    canonical_snapshot_id: UUID | None = None
    mapping_scope_id: UUID | None = None
    execute_plan_id: UUID | None = None
    selected_canonical_rule_ids: list[str] | None = None
    migration_name: str | None = None
    selected_sdwan_target_id: str | None = None


def get_context() -> SessionContext:
    if "session_context" not in st.session_state:
        st.session_state.session_context = SessionContext()
    return st.session_state.session_context


def context_as_dict() -> dict[str, str | None]:
    context = get_context()
    return {
        key: str(value) if value is not None else None
        for key, value in asdict(context).items()
    }
