"""
streamlit_app.py -- the owner application's entry point on Streamlit Community Cloud.

A router and nothing else. Every figure, definition, posture, finding, movement, forecast and
answer on every page is produced by the existing deterministic engine and consumed here as a
finished owner-safe projection. This file, and everything under `owner_app/`, computes no
business value.

The authority chain is unchanged and runs entirely below this layer:

    Evidence -> Validation -> Semantic Layer -> Trust Gate -> Metric Engine -> Analytics Engine
    -> Business Insight Engine -> Answer Contract -> AI Business Analyst -> this UI

ACCESS. There is no login screen: the owner opens a private, unlisted URL, and that URL is the
credential. No secret reaches the browser -- the database connection string and the language
model's key are read from the server-side environment by the engine, and nothing in `owner_app/`
renders them.
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Owner Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from owner_app import runtime                                    # noqa: E402
from owner_app.views import (analyst, analytics, decisions,      # noqa: E402
                             definitions, home, insights, powerbi, quality)

# Owner Home first, deliberately: the owner's own summary is the front door, and the analyst
# surfaces sit behind it.
PAGES = (
    ("Owner Home", lambda: home.render()),
    ("Financial", lambda: analytics.render("financial")),
    ("Operations", lambda: analytics.render("operations")),
    ("Risk & Data Quality", lambda: quality.render()),
    ("Insights", lambda: insights.render()),
    ("AI Business Analyst", lambda: analyst.render()),
    ("Analytics workspace", lambda: powerbi.render()),
    ("Decisions", lambda: decisions.render()),
    ("Definitions & trust", lambda: definitions.render()),
)


def main() -> None:
    labels = [label for label, _ in PAGES]

    with st.sidebar:
        st.markdown("### Owner Intelligence")
        chosen = st.radio("Go to", labels, key="nav", label_visibility="collapsed")
        st.divider()
        _footer()

    # Building the engine's payloads takes tens of seconds on a cold process. It happens once,
    # here, with something on screen -- rather than silently inside the first page's first call.
    with st.spinner("Reading the trusted export..."):
        runtime.service()

    render = dict(PAGES)[chosen]
    render()


def _footer() -> None:
    """What the application is reading, said plainly. No credential is shown or held here."""
    try:
        descriptor = runtime.source_descriptor()
    except Exception:
        return

    st.caption(f"Records as at {descriptor.as_of}")
    st.caption("Every figure is produced by the deterministic analytics engine. Where the "
               "records hold more than one definition, all of them are shown and none is "
               "chosen.")

    with st.expander("About this data"):
        st.write(f"**Source** — {descriptor.name} ({descriptor.kind})")
        st.write(f"**Status** — {descriptor.status}")
        if descriptor.notes:
            st.caption(descriptor.notes)
        try:
            llm = runtime.llm_status()
            st.write(f"**Language layer** — {llm.get('status', '')}")
            st.caption(llm.get("note", ""))
        except Exception:
            pass


main()
