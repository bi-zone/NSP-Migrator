from __future__ import annotations

from typing import Any

import streamlit as st

from app.core.errors import DomainValidationError
from app.modules.imports.application.dto import ImportVendorDTO
from app.modules.imports.application.use_cases.create_import_source import (
    CreateImportSourceCommand,
)
from app.modules.imports.application.use_cases.get_import_vendors import (
    GetImportVendorsQuery,
)
from app.modules.imports.application.use_cases.upload_artifact import (
    UploadArtifactCommand,
)
from app.modules.imports.cisco_asa.application.use_cases.run_cisco_mapping import (
    RunCiscoMappingCommand,
)
from streamlit_app.services.use_cases import (
    get_create_import_source,
    get_import_vendors,
    get_run_cisco_mapping,
    get_upload_artifact,
    run_async,
)
from streamlit_app.session.context import context_as_dict, get_context


def render() -> None:
    st.title("Upload")

    mode = st.segmented_control(
        "Upload mode",
        options=["Configuration file", "API"],
        default="Configuration file",
        label_visibility="collapsed",
        key="upload_rules_mode",
    )

    if mode == "Configuration file":
        _render_file_upload()
        _render_map_uploaded_snapshot_action()
        return

    _render_api_upload()


def _render_file_upload() -> None:
    with st.spinner("Loading vendors..."):
        vendors_result = run_async(
            get_import_vendors().execute(GetImportVendorsQuery())
        )
    vendors = vendors_result.vendors

    if not vendors:
        st.warning("No vendors found in DB")
        return

    vendor_options = [vendor.code for vendor in vendors]
    vendor_by_code = {vendor.code: vendor for vendor in vendors}
    default_index = _resolve_default_vendor_index(vendor_options)

    with st.form("upload_rules_file_form"):
        col_vendor, col_upload = st.columns([4, 1])
        with col_vendor:
            vendor_code = st.selectbox(
                "Vendor",
                options=vendor_options,
                index=default_index,
                format_func=lambda code: _vendor_label(vendor_by_code[code]),
            )
            source_name = st.text_input(
                "Source name",
                value=f"{vendor_code}-upload",
                help="Unique name for uploaded source in snapshots list.",
            )
        with col_upload:
            upload_submitted = st.form_submit_button(
                "Upload",
                type="primary",
                use_container_width=True,
            )

        st.markdown(
            '<div class="dropzone-title">Upload config file</div>',
            unsafe_allow_html=True,
        )
        uploaded_file = st.file_uploader(
            "Config file",
            type=["txt", "cfg"],
            label_visibility="collapsed",
            help="Accepted formats: .txt, .cfg",
        )

    if not upload_submitted:
        return

    if not uploaded_file:
        st.error("Please select a config file before uploading.")
        return

    raw_bytes = uploaded_file.getvalue()
    if not raw_bytes:
        st.error("Uploaded file is empty.")
        return

    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        st.error("Config file must be UTF-8 encoded text.")
        return

    source_name = source_name.strip()
    if not source_name:
        st.error("Source name is required.")
        return

    try:
        with st.spinner("Uploading configuration file..."):
            source_result, upload_result = run_async(
                _submit_file_upload(
                    vendor_code=vendor_code,
                    source_name=source_name,
                    file_name=uploaded_file.name or "config.cfg",
                    raw_text=raw_text,
                )
            )
    except DomainValidationError as error:
        st.error(str(error))
        return
    except Exception as error:
        st.error(f"Upload failed: {error}")
        with st.expander("Error details"):
            st.exception(error)
        return

    context = get_context()
    context.source_id = source_result.source.id
    context.source_name = source_result.source.name
    context.vendor_code = source_result.source.vendor_code
    context.upload_id = upload_result.upload.id
    context.snapshot_id = upload_result.snapshot.id

    if source_result.created:
        st.success("Upload completed successfully.")
    else:
        st.success("Upload completed successfully. Existing source was reused.")

    st.caption(
        f"source_id={source_result.source.id} | snapshot_id={upload_result.snapshot.id}"
    )
    with st.expander("Session context"):
        st.json(context_as_dict())


def _render_api_upload() -> None:
    with st.form("upload_rules_api_form"):
        col_form, col_submit = st.columns([4, 1])
        with col_form:
            st.selectbox("Vendor", options=["Cisco"], index=0)
            st.text_input("IP/DN", value="172.18.0.50")
            st.selectbox("API version", options=["2.2"], index=0)
            st.text_input("Login", value="tech_user_ro")
            st.text_input("Password", value="password", type="password")
        with col_submit:
            submit = st.form_submit_button(
                "Upload",
                type="primary",
                use_container_width=True,
            )

    if submit:
        st.warning("API upload is not implemented yet. Use Configuration file mode.")


def _render_map_uploaded_snapshot_action() -> None:
    context = get_context()
    st.markdown("### Map to canonical")
    if context.snapshot_id is None:
        st.caption("Upload config first, then map it to canonical.")
        return

    st.caption(f"Uploaded snapshot: `{context.snapshot_id}`")
    if st.button(
        "Map",
        type="primary",
        key="upload_map_button",
    ):
        with st.spinner("Mapping to canonical..."):
            result = run_async(
                get_run_cisco_mapping().execute(
                    RunCiscoMappingCommand(source_snapshot_id=context.snapshot_id)
                )
            )
        context.canonical_snapshot_id = result.canonical_snapshot_id
        st.success(
            f"Canonical snapshot ready: {result.canonical_snapshot_id}. Existing result reused when available."
        )


def _resolve_default_vendor_index(vendor_options: list[str]) -> int:
    if "cisco_asa" in vendor_options:
        return vendor_options.index("cisco_asa")
    return 0


def _vendor_label(vendor: ImportVendorDTO) -> str:
    return vendor.display_name or vendor.code


async def _submit_file_upload(
    *,
    vendor_code: str,
    source_name: str,
    file_name: str,
    raw_text: str,
) -> tuple[Any, Any]:
    source_result = await get_create_import_source().execute(
        CreateImportSourceCommand(
            vendor_code=vendor_code,
            name=source_name,
            active=True,
        )
    )
    upload_result = await get_upload_artifact().execute(
        UploadArtifactCommand(
            source_id=source_result.source.id,
            file_name=file_name,
            raw_text=raw_text,
            uploaded_by="streamlit",
        )
    )
    return source_result, upload_result
