"""
home.py -- Owner Home.

The same four blocks the existing Owner Home renders, in the same order and from the same
payload: the snapshot, what needs attention, what the business did, and what is worth knowing.
The grouping and the counts are the engine's -- `attention_subjects` is one entry per business
subject and the headline counts subjects, so a subject the records raise three findings about is
one thing to deal with rather than three.
"""
from __future__ import annotations

import streamlit as st

from owner_app import runtime, ui


def render() -> None:
    home = runtime.owner_home()

    st.title("Owner Home")
    ui.as_of_line(home)

    _snapshot(home)
    _attention(home)
    _movements(home)
    _worth_knowing(home)

    ui.limitations(home.get("limitations"))


def _snapshot(home: dict) -> None:
    ui.section_heading(
        "Executive snapshot",
        "Every figure is the engine's. A measure whose definitions disagree shows all of them "
        "and no headline.")

    for label, key in (("Business health", "business_health"),
                       ("Operations", "operations"),
                       ("Risk indicators", "risks")):
        tiles = home.get(key) or []
        if not tiles:
            continue
        st.markdown(f"##### {label}")
        ui.tile_grid(tiles, columns=3, key_prefix=key)

    trust = home.get("trust_summary") or {}
    if trust:
        st.markdown("##### Which numbers can I trust?")
        # The gate's own census, in the owner's words. The counts are the engine's and the
        # canonical level behind each phrase is not shown here.
        columns = st.columns(len(trust))
        for column, entry in zip(columns, trust.values()):
            column.metric(entry.get("owner_status", ""), f"{entry.get('count', 0)} measures")
        for entry in trust.values():
            st.caption(f"{entry.get('owner_status', '')} — {entry.get('owner_explanation', '')}")


def _attention(home: dict) -> None:
    subjects = home.get("attention_subjects") or []
    ui.section_heading("What needs my attention", count=len(subjects))

    if not subjects:
        st.success("Nothing in the records is waiting on a decision or a review. This is what "
                   "the evidence says, not an empty view.")
        return

    # The breakdown, counted from the groups themselves rather than written here.
    counts: dict[str, int] = {}
    for group in subjects:
        label = group.get("action_category_label", "")
        counts[label] = counts.get(label, 0) + 1
    if len(counts) > 1:
        st.caption(" · ".join(f"{n} × {label.lower()}" for label, n in counts.items()))

    for group in subjects:
        ui.subject_card(group)


def _movements(home: dict) -> None:
    movements = home.get("movements") or []
    changes = home.get("changes") or []
    ui.section_heading(
        "What the business did", count=len(movements),
        note="Complete periods only, so a part-month is never shown as a movement. Direction "
             "only: your records set no threshold for what counts as a significant move.")

    if not movements and not changes:
        st.info("No period-over-period movement is established on the current evidence.")
        return

    for card in movements:
        ui.insight_card(card)

    if changes:
        st.markdown("##### Compared side by side")
        for change in changes:
            ui.movement_card(change)


def _worth_knowing(home: dict) -> None:
    findings = home.get("findings") or []
    supporting = home.get("supporting") or []
    ui.section_heading("Worth knowing", count=len(findings),
                       note="Recorded because the records show it. Nothing here asks anything "
                            "of you.")
    if not findings:
        st.caption("Nothing else is recorded about the current evidence.")
    for card in findings:
        ui.insight_card(card)

    if supporting:
        ui.section_heading("Supporting information", count=len(supporting))
        for card in supporting:
            ui.insight_card(card)

    actions = home.get("recommended_actions") or []
    if actions:
        ui.section_heading("Suggested next steps", count=len(actions))
        for action in actions:
            with st.container(border=True):
                if action.get("guidance"):
                    ui.guidance_block(action["guidance"])
                else:
                    st.write(action.get("recommendation", ""))
                if action.get("confidence"):
                    st.caption(f"Confidence: {action['confidence']}")
