"""
decisions.py -- what the owner has decided about the disagreements the evidence cannot settle.

WHAT A RECORDED DECISION IS, AND IS NOT
---------------------------------------
It is a note about what management is doing. It is NOT a resolution of anything.

The engine never reads it back. After an owner records a preferred business definition, the
measure still carries the same posture, still shows every competing definition, and still refuses
a single headline where the gate refuses one. The disagreement in the records is a fact; the
preference is a policy sitting beside it, and confusing the two would be the one thing this whole
product exists to prevent.

That is why the strongest status here is worded as a PREFERRED BUSINESS DEFINITION and never as a
resolved conflict. The stored value is unchanged -- the store's statuses, keys and history are
exactly what they were -- and only the sentence an owner reads is stated accurately.
"""
from __future__ import annotations

import streamlit as st

from owner_app import runtime

# The store's own statuses, said the way they are true. `resolved` records that management has
# named a preferred definition; it does not record that a conflict went away.
STATUS_WORDING = {
    "open": "Not yet reviewed",
    "under_review": "Under review",
    "resolved": "Preferred business definition recorded",
}


def render() -> None:
    st.title("Owner decisions")
    st.caption(
        "Where management stands on each disagreement the records cannot settle. Recording a "
        "preference changes nothing upstream: every competing definition stays visible, every "
        "figure stays as it was, and each measure keeps the posture its own evidence carries.")

    log = runtime.decision_log()
    items = log.get("items") or []
    statuses = log.get("statuses") or []

    if not items:
        st.success("Nothing is awaiting a decision on the current evidence.")
        return

    status_keys = [s.get("key") for s in statuses]
    status_labels = [STATUS_WORDING.get(s.get("key"), s.get("label", "")) for s in statuses]

    for index, item in enumerate(items):
        _item(item, index, status_keys, status_labels)


def _item(item: dict, index: int, status_keys: list, status_labels: list) -> None:
    key = item.get("item_key") or item.get("insight_id") or f"item-{index}"
    current = item.get("status") or "open"

    with st.container(border=True):
        heading, badge = st.columns([4, 1])
        heading.markdown(f"**{item.get('title', '')}**")
        badge.caption(STATUS_WORDING.get(current, item.get("status_label", "")))

        if item.get("owner_facing"):
            st.caption(item["owner_facing"])
        if item.get("decision"):
            st.write(item["decision"])
        if item.get("note"):
            st.caption(f"Your note: {item['note']}")

        with st.expander("Record where this stands"):
            chosen_label = st.radio(
                "Status", status_labels,
                index=status_keys.index(current) if current in status_keys else 0,
                key=f"status-{key}")
            chosen = status_keys[status_labels.index(chosen_label)]
            note = st.text_area("Note (optional)", value=item.get("note", ""),
                                key=f"note-{key}", height=80)
            decided_by = st.text_input("Recorded by (optional)",
                                       value=item.get("decided_by", ""), key=f"by-{key}")

            if chosen == "resolved":
                st.caption(
                    "This records which definition the business treats as official. It does not "
                    "remove the other definitions, change any figure, or alter the measure's "
                    "posture — all of them stay exactly as they are.")

            if st.button("Save", key=f"save-{key}"):
                runtime.record_decision(key, chosen, note=note, decided_by=decided_by)
                st.success("Recorded. Nothing upstream changed.")
                st.rerun()
