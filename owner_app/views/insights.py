"""
insights.py -- the whole feed, grouped by what each item asks of the owner.

The grouping is the engine's: every card carries the action category the deterministic layer
assigned it, and this page groups by that rather than deciding for itself what counts as
attention. That is why a validated revenue rise appears under movements and not on the work list.
"""
from __future__ import annotations

import streamlit as st

from owner_app import runtime, ui


def render() -> None:
    home = runtime.owner_home()

    st.title("Insights & Attention")
    ui.as_of_line(home)

    summary = home.get("action_summary") or []
    if summary:
        columns = st.columns(len(summary))
        for column, entry in zip(columns, summary):
            column.metric(entry.get("label", ""), entry.get("count", 0))
        for entry in summary:
            st.caption(f"**{entry.get('label', '')}** — {entry.get('meaning', '')}")

    blocks = (
        ("Needs attention", home.get("needs_attention"),
         "Only what someone has to act on. A movement is not work, so it is not here."),
        ("Business movements", home.get("movements"),
         "Direction only, over complete periods. Your records set no threshold for what counts "
         "as a significant move, so none is applied."),
        ("Worth knowing", home.get("findings"),
         "Nothing to correct. It changes how the affected figures should be read."),
        ("Supporting information", home.get("supporting"), ""),
    )

    for title, cards, note in blocks:
        cards = cards or []
        if not cards and title == "Supporting information":
            continue
        ui.section_heading(title, count=len(cards), note=note)
        if not cards:
            st.caption("Nothing in this group on the current evidence. That is what the records "
                       "say, not a gap in the view.")
        for card in cards:
            ui.insight_card(card)
