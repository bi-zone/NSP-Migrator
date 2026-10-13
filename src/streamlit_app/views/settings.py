from typing import Any

import streamlit as st

from app.modules.settings.csp_profiles.application.change_profile_active_status import (
    ChangeProfileActiveStatusCommand,
)
from app.modules.settings.csp_profiles.application.check_profile_connection import (
    TestProfileConnectionCommand,
)
from app.modules.settings.csp_profiles.application.create_profile import (
    CreateProfileCommand,
)
from app.modules.settings.csp_profiles.application.delete_profile import (
    DeleteProfileCommand,
)
from app.modules.settings.csp_profiles.application.dto import (
    CertificateBundleDTO,
    CSPProfileDTO,
)
from app.modules.settings.csp_profiles.application.list_profiles import (
    ListProfilesQuery,
)
from app.modules.settings.csp_profiles.application.remove_profile_password import (
    RemoveProfilePasswordCommand,
)
from app.modules.settings.csp_profiles.application.update_profile import (
    UNSET,
    UpdateProfileCommand,
)
from app.modules.settings.csp_profiles.domain.enums import CertificateBundleFormat
from streamlit_app.services.use_cases import (
    get_change_profile_active_status,
    get_create_csp_profile,
    get_csp_profiles,
    get_delete_csp_profile,
    get_remove_csp_profile_password,
    get_test_csp_profile_connection,
    get_update_csp_profile,
    run_async,
)


def render() -> None:
    st.title("Settings")
    st.caption("Manage encrypted CSP connection profiles.")

    _render_create_profile()
    profiles = _load_profiles()
    if profiles is None:
        return

    _render_profiles_table(profiles)
    if profiles:
        _render_profile_editor(profiles)


def _render_create_profile() -> None:
    with st.expander("Create CSP profile", expanded=False):
        cert_protected = st.checkbox(
            "Certificate is password-protected",
            key="create_csp_certificate_protected",
        )
        with st.form("create_csp_profile", clear_on_submit=True):
            name = st.text_input("Name")
            base_url = st.text_input("CSP URL", placeholder="https://csp.example")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            certificate = st.file_uploader(
                "Client certificate (PEM, P12, or PFX)",
                type=["pem", "p12", "pfx"],
                key="create_csp_certificate",
            )
            passphrase = ""
            if cert_protected:
                passphrase = st.text_input(
                    "Certificate passphrase",
                    type="password",
                )
            submitted = st.form_submit_button("Create profile", type="primary")

        if not submitted:
            return
        try:
            bundle_data, bundle_format = _read_uploaded_certificate(certificate)
            run_async(
                get_create_csp_profile().execute(
                    CreateProfileCommand(
                        name=name,
                        base_url=base_url,
                        username=username,
                        password=_read_password(password),
                        certificate_bundle=CertificateBundleDTO(
                            data=bundle_data,
                            format=bundle_format,
                            passphrase=_read_certificate_passphrase(
                                protected=cert_protected,
                                value=passphrase,
                            ),
                        ),
                    )
                )
            )

        except Exception as exc:
            st.error(str(exc))
            return

        st.success("CSP profile created.")
        st.rerun()


def _load_profiles() -> list[CSPProfileDTO] | None:
    try:
        return list(
            run_async(
                get_csp_profiles().execute(query=ListProfilesQuery(active_only=False))
            ).profiles
        )
    except Exception as exc:
        st.error(str(exc))
        return None


def _render_profiles_table(profiles: list[CSPProfileDTO]) -> None:
    st.subheader("CSP profiles")
    if not profiles:
        st.info("No CSP profiles configured.")
        return

    st.dataframe(
        [
            {
                "Name": profile.name,
                "URL": profile.base_url,
                "Is Active": profile.is_active,
                "Username": profile.username,
                "Auth": profile.auth_type,
                "Password": profile.has_password,
                "Private key": profile.certificate_has_private_key,
                "Certificate expires": profile.certificate_not_after,
            }
            for profile in profiles
        ],
        width="stretch",
        hide_index=True,
    )


def _render_profile_editor(profiles: list[CSPProfileDTO]) -> None:
    profiles_by_id = {str(profile.id): profile for profile in profiles}
    selected_id = st.selectbox(
        "Profile to manage",
        options=list(profiles_by_id),
        format_func=lambda profile_id: profiles_by_id[profile_id].name,
    )
    profile: CSPProfileDTO = profiles_by_id[selected_id]

    cert_protected = st.checkbox(
        "Certificate is password-protected",
        key=f"edit_csp_certificate_protected_{profile.id}",
    )
    with st.form(f"edit_csp_profile_{profile.id}"):
        name = st.text_input("Name", value=profile.name)
        base_url = st.text_input("CSP URL", value=profile.base_url)
        username = st.text_input("Username", value=profile.username)
        password = st.text_input(
            "New password (leave blank to preserve)",
            type="password",
        )
        certificate = st.file_uploader(
            "New client certificate PEM, P12, or PFX (leave empty to preserve)",
            type=["pem", "p12", "pfx"],
            key=f"edit_csp_certificate_{profile.id}",
        )
        passphrase = ""
        if cert_protected:
            passphrase = st.text_input(
                "Certificate passphrase",
                type="password",
                key=f"edit_csp_certificate_passphrase_{profile.id}",
            )
        save = st.form_submit_button("Save changes", type="primary")

    if save:
        _update_profile(
            profile,
            name=name,
            base_url=base_url,
            username=username,
            password=password,
            certificate=certificate,
            cert_protected=cert_protected,
            passphrase=passphrase,
        )

    first, second, third, fourth = st.columns(4)
    with first:
        if st.button("Test connection", key=f"test_csp_{profile.id}"):
            _test_connection(profile)

    with second:
        if profile.is_active:
            if st.button(
                "Deactivate",
                key=f"deactivate_csp_profile_{profile.id}",
            ):
                _change_active_status(profile, new_status=False)

        else:  # if profile not active
            if st.button(
                "Activate",
                key=f"activate_csp_profile_{profile.id}",
            ):
                _change_active_status(profile, new_status=True)

    with third:
        if st.button(
            "Remove password",
            key=f"remove_csp_password_{profile.id}",
            disabled=not profile.has_password,
        ):
            _remove_password(profile)

    with fourth:
        confirmed = st.checkbox(
            "Confirm deletion",
            key=f"confirm_csp_delete_{profile.id}",
        )
        if st.button(
            "Delete profile",
            key=f"delete_csp_{profile.id}",
            type="secondary",
            disabled=not confirmed,
        ):
            _delete_profile(profile)


def _update_profile(
    profile: CSPProfileDTO,
    *,
    name: str,
    base_url: str,
    username: str,
    password: str,
    certificate: Any,
    cert_protected: bool,
    passphrase: str,
) -> None:
    try:
        certificate_data: Any = UNSET
        certificate_format: Any = UNSET
        if certificate is not None:
            certificate_data, certificate_format = _read_uploaded_certificate(
                certificate
            )
        certificate_passphrase: Any = UNSET
        if cert_protected:
            if certificate is None:
                raise ValueError(
                    "Certificate passphrase requires a new certificate file"
                )
            certificate_passphrase = _read_certificate_passphrase(
                protected=True,
                value=passphrase,
            )
        run_async(
            get_update_csp_profile().execute(
                UpdateProfileCommand(
                    profile_id=profile.id,
                    name=name,
                    base_url=base_url,
                    username=username,
                    password=password or UNSET,
                    certificate_bundle=CertificateBundleDTO(
                        data=certificate_data,
                        format=certificate_format,
                        passphrase=certificate_passphrase
                        if certificate_passphrase is not UNSET
                        else None,
                    )
                    if certificate_data is not UNSET
                    else UNSET,
                )
            )
        )
    except Exception as exc:
        st.error(str(exc))
        return
    st.success("CSP profile updated.")
    st.rerun()


def _test_connection(profile: CSPProfileDTO) -> None:
    try:
        with st.spinner("Connecting to CSP..."):
            result = run_async(
                get_test_csp_profile_connection().execute(
                    TestProfileConnectionCommand(profile_id=profile.id)
                )
            )
    except Exception as exc:
        st.error(str(exc))
        return

    st.success("Connection established.")
    st.dataframe(
        [
            {
                "VPC ID": vpc.vpc_id,
                "Customer": vpc.customer_name,
                "Project": vpc.project_name,
                "CUID": vpc.cuid,
                "PID": vpc.pid,
            }
            for vpc in result.allowed_vpcs
        ],
        width="stretch",
        hide_index=True,
    )


def _remove_password(profile: CSPProfileDTO) -> None:
    try:
        run_async(
            get_remove_csp_profile_password().execute(
                RemoveProfilePasswordCommand(
                    profile_id=profile.id,
                )
            )
        )
    except Exception as exc:
        st.error(str(exc))
        return
    st.success("Profile password removed.")
    st.rerun()


def _change_active_status(profile: CSPProfileDTO, new_status: bool) -> None:
    try:
        run_async(
            get_change_profile_active_status().execute(
                ChangeProfileActiveStatusCommand(
                    profile_id=profile.id,
                    new_status=new_status,
                )
            )
        )
    except Exception as exc:
        st.error(str(exc))
        return
    st.success("Profile active status changed.")
    st.rerun()


def _delete_profile(profile: CSPProfileDTO) -> None:
    try:
        run_async(
            get_delete_csp_profile().execute(
                DeleteProfileCommand(
                    profile_id=profile.id,
                )
            )
        )
    except Exception as exc:
        st.error(str(exc))
        return
    st.success("CSP profile deleted.")
    st.rerun()


def _read_password(value: str) -> str:
    if not value:
        raise ValueError("Password is required")
    return value


def _read_uploaded_certificate(
    uploaded_file: Any,
) -> tuple[bytes, CertificateBundleFormat]:
    payload = _read_bundle(uploaded_file)
    name = getattr(uploaded_file, "name", "") or ""
    try:
        return payload, CertificateBundleFormat.from_filename(name)
    except ValueError:
        raise ValueError(
            "Client certificate must be a .pem, .p12, or .pfx file"
        ) from None


def _read_bundle(uploaded_file: Any) -> bytes:
    if uploaded_file is None:
        raise ValueError("Client certificate is required")
    try:
        payload = uploaded_file.getvalue()
    except AttributeError as exc:
        raise ValueError("Client certificate is required") from exc
    if not payload:
        raise ValueError("Client certificate must not be empty")
    return payload


def _read_certificate_passphrase(*, protected: bool, value: str) -> str | None:
    if not protected:
        return None
    if not value:
        raise ValueError("Certificate passphrase is required")
    return value
