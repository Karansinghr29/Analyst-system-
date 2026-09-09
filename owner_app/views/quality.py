"""
quality.py -- the data-quality register, owner-first.

Every finding the engine holds, each projected into the three sentences an owner needs: what is
happening, why it matters, what to do. The action is derived from the finding's own KIND -- what
kind of thing it is -- which the engine decided from the finding's recorded issue, root cause,
confidence, status and fixability. Never from its severity: how bad a finding is and what can be
done about it are different questions.

The recorded wording, the severity, the evidence references and the root cause are all still
here, inside the technical panel. They are not the default view.
"""
from __future__ import annotations

import streamlit as st

from owner_app import runtime, ui

SEVERITY_LABELS = {
    "CRITICAL": "Critical", "HIGH": "High", "MEDIUM": "Medium",
    "LOW": "Low", "INFORMATIONAL": "Informational", "UNVERIFIED": "Not yet verified",
}


def render() -> None:
    payload = runtime.data_quality()

    st.title("Risk & Data Quality")
    st.caption("What the records say about themselves. This page covers the whole business: it "
               "is not narrowed by a filter chosen elsewhere.")

    st.metric("Recorded findings", payload.get("total", 0))

    # Counted by what each finding ASKS FOR, beside the usual severity tally. Severity says how
    # bad; the action category says who has to do something about it.
    categories = payload.get("action_categories") or []
    if categories:
        columns = st.columns(len(categories))
        for column, entry in zip(columns, categories):
            column.metric(entry.get("label", ""), entry.get("count", 0))
        for entry in categories:
            st.caption(f"**{entry.get('label', '')}** — {entry.get('meaning', '')}")

    severities = payload.get("severities") or []
    labels = [SEVERITY_LABELS.get(g.get("severity"), g.get("severity", ""))
              for g in severities]
    if not severities:
        st.success("No finding is recorded against the current evidence.")
        return

    chosen = st.radio("Show", ["All"] + labels, horizontal=True, key="dq-severity")

    for group in severities:
        label = SEVERITY_LABELS.get(group.get("severity"), group.get("severity", ""))
        if chosen != "All" and chosen != label:
            continue
        ui.section_heading(label, count=group.get("count", 0))
        for issue in group.get("issues") or []:
            _finding(issue)


def _finding(issue: dict) -> None:
    with st.container(border=True):
        st.markdown(f"**{issue.get('owner_what') or issue.get('owner_issue', '')}**")
        st.caption(issue.get("owner_category_label", ""))
        if issue.get("owner_why"):
            st.write(issue["owner_why"])
        if issue.get("owner_action"):
            st.info(issue["owner_action"])

        # The register's own record, in the register's own words. This is where the identifiers,
        # object names and canonical postures belong.
        ui.technical_panel("Evidence & technical details", {
            "Finding reference": issue.get("dq_id"),
            "Recorded wording": issue.get("issue"),
            "Kind of finding": str(issue.get("owner_action_kind", "")).replace("_", " "),
            "Business area": issue.get("business_area"),
            "Affected rows": issue.get("affected_rows"),
            "Affected amount": issue.get("affected_amount"),
            "Affected measures": issue.get("owner_measure_names"),
            "Measure references": issue.get("affected_metrics"),
            "Trust levels affected": issue.get("affected_trust_levels"),
            "Root cause": issue.get("root_cause"),
            "Root-cause confidence": issue.get("root_cause_confidence"),
            "Status": issue.get("status"),
            "Evidence": issue.get("evidence"),
            "Recorded handling": issue.get("recommended_investigation"),
        })
