"""
definitions.py -- what each measure means, and where the records disagree about one.

Everything on this page comes from the metric semantic contract the engine already builds. The
contract itself says which of its fields may be shown to an owner -- `owner_safe_fields` -- so
this page asks it rather than judging for itself which registry prose is readable. A definition
naming an application function is the right words for the audit trail and the wrong ones here, so
it appears in the technical panel instead.
"""
from __future__ import annotations

import streamlit as st

from owner_app import runtime, ui


def render() -> None:
    st.title("Definitions & trust")

    unresolved = runtime.unresolved_definitions()
    measures = unresolved.get("measures") or []
    needing_decision = unresolved.get("decision_required") or []

    ui.section_heading(
        "Where the records disagree", count=len(measures),
        note="Each of these is measured more than one defensible way, and the answers differ. "
             "The system will not choose between them.")

    if needing_decision:
        st.warning(f"{len(needing_decision)} of these are waiting on a management decision.")

    for measure in measures:
        with st.container(border=True):
            st.markdown(f"**{measure.get('measure', '')}**")
            st.caption(f"{measure.get('owner_status', '')} · "
                       f"{measure.get('definition_count', 0)} definitions")
            st.write(measure.get("why_no_single_figure", ""))
            if not measure.get("definitions_computable", True):
                st.caption("The competing definitions are not computable in the current engine, "
                           "so the disagreement is shown without figures rather than implying "
                           "two comparable numbers exist.")

    _catalogue()


def _catalogue() -> None:
    contracts = (runtime.metric_contracts() or {}).get("metrics") or []
    if not contracts:
        return

    ui.section_heading("Every measure, and what it means", count=len(contracts))

    names = [c.get("business_name", "") for c in contracts]
    chosen = st.selectbox("Measure", names, key="contract-measure")
    contract = contracts[names.index(chosen)]
    safe = set(contract.get("owner_safe_fields") or ())

    st.markdown(f"### {contract.get('business_name', '')}")
    st.caption(contract.get("owner_status", ""))

    if "business_question" in safe and contract.get("business_question"):
        st.write(contract["business_question"])

    rows = (
        ("What it is", "definition"),
        ("One row of it is", "grain"),
        ("Periods it covers", "supported_period"),
        ("It can be split by", "supported_dimensions"),
        ("Limitations", "limitations"),
    )
    for label, field in rows:
        if field in safe and contract.get(field):
            st.markdown(f"**{label}** — {contract[field]}")

    st.markdown(f"**When definitions compete** — {contract.get('conflict_behaviour', '')}")
    st.markdown(f"**What this asks of you** — {contract.get('owner_action', '')}")

    left, right = st.columns(2)
    left.metric("Usable on its own in a decision",
                "Yes" if contract.get("usable_for_decisions") else "No")
    right.metric("Comparable over time",
                 "Yes" if contract.get("comparable_over_time") else "No")
    st.caption(contract.get("usable_for_decisions_note", ""))
    st.caption(contract.get("comparable_over_time_note", ""))

    # The fields the contract did NOT mark owner-safe: the registry's own words, which name
    # application objects and columns. Kept, behind the expander.
    ui.technical_panel("Evidence & technical details", {
        "Reference": contract.get("metric_id"),
        "Trust level": contract.get("trust_level"),
        **{label: contract.get(field) for label, field in rows if field not in safe},
    })
