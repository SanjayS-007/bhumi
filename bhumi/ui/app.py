import streamlit as st

st.set_page_config(page_title="BHUMI", layout="wide")

st.title("BHUMI")
st.caption("Coal-sector document intelligence — MVP-1: acquire, read, drill down")

try:
    from bhumi.config.settings import get_settings

    s = get_settings()
    st.info(
        f"profile **{s.profile.value}** · Tier-3 OCR unavailable (no GPU on this machine) · "
        f"data dir `{s.data_dir.resolve()}`",
        icon="⚙️",
    )
except Exception as e:  # pragma: no cover
    st.error(f"settings failed to load: {e}")

st.markdown(
    """
Use the sidebar to navigate:
- **1 Corpus** — registered documents and their read status
- **2 Document Explorer** — click a table cell, see it outlined on the source page

If the corpus is empty, run `uv run task ingest -- --sample` first.
"""
)
