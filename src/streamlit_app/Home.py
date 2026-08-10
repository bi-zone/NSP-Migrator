from pathlib import Path

import streamlit as st

from streamlit_app.views import (
    canonical_rules,
    execute_rules,
    mapped_rules,
    reports,
    settings,
    trace_rules,
    upload_rules,
)


def _inject_custom_css() -> None:
    css_path = Path(__file__).parent / "assets" / "custom.css"
    if not css_path.exists():
        return
    st.markdown(
        f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True
    )


def main() -> None:
    st.set_page_config(
        page_title="Rules Migrator",
        page_icon="🛡️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_custom_css()

    pages = [
        st.Page(
            upload_rules.render,
            title="Upload rules",
            icon="📤",
            url_path="upload-rules",
            default=True,
        ),
        st.Page(
            trace_rules.render,
            title="Trace",
            icon="🧭",
            url_path="trace-rules",
        ),
        st.Page(
            canonical_rules.render,
            title="Canonical rules",
            icon="📋",
            url_path="canonical-rules",
        ),
        st.Page(
            mapped_rules.render,
            title="Mapped rules",
            icon="🧭",
            url_path="mapped-rules",
        ),
        st.Page(
            execute_rules.render,
            title="Execute rules",
            icon="🚀",
            url_path="execute-rules",
        ),
        st.Page(
            reports.render,
            title="Reports",
            icon="📊",
            url_path="reports",
        ),
        st.Page(
            settings.render,
            title="Settings",
            icon="⚙️",
            url_path="settings",
        ),
    ]

    with st.sidebar:
        st.markdown(
            '<div class="username-box">&lt;Username&gt;</div>', unsafe_allow_html=True
        )

    navigation = st.navigation(pages)
    navigation.run()


if __name__ == "__main__":
    main()
