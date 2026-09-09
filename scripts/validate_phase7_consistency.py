"""
validate_phase7_consistency.py -- proves the Phase 7 specification is consistent with the
Phase 1-6 artifacts it claims to build on.

The Phase 7 brief requires this explicitly: "First produce the complete Phase 7 blueprint and
validate that it is consistent with all Phase 1-6 artifacts."

A specification phase produces prose, and prose drifts. This script is the guard: it reads every
Phase 7 document and registry, extracts every metric_id, conflict_id, dq_id, trust level and
capability they mention, and checks each against the LIVE system. A document that names a metric
the registry does not contain, or claims a trust level the gate does not assign, fails here --
so the blueprint cannot quietly describe a system other than the one that exists.

Checks performed:
  1. Every metric_id mentioned in any Phase 7 doc/registry exists in semantic_metric_registry.csv
  2. Every trust level asserted matches engine/gate.py's verdict
  3. Every conflict_id / dq_id exists in conflicts.md / data_quality_registry.csv
  4. No dashboard tile permits a headline the trust policy forbids
  5. No role view permits a conclusion the trust policy forbids
  6. Every conflict that must stay visible is present on every declared surface
  7. Every capability named is in analysis_capability_registry.csv
  8. The exact NOT_DETERMINABLE phrase is used wherever a doc claims it is
  9. No Phase 7 doc invents a threshold, benchmark, or causal claim

Read-only. Modifies nothing.
"""
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from engine import analyst_roles

NOT_DET = "Not determinable from exported evidence."

PHASE7_DOCS = (
    "phase7_product_architecture.md", "owner_experience_spec.md",
    "role_based_analytics_spec.md", "bi_dashboard_spec.md",
    "proactive_insight_system_spec.md", "decision_support_spec.md",
    "business_analyst_ai_spec.md", "conversation_dashboard_integration_spec.md",
    "production_ai_architecture.md", "powerbi_analytics_mapping.md",
    "business_question_matrix.md", "final_system_capabilities.md",
    "phase7_implementation_roadmap.md",
)

PHASE7_REGISTRIES = ("owner_dashboard_registry.csv", "role_view_registry.csv",
                     "conflict_disclosure_registry.csv")

_METRIC = re.compile(r"\bM\.[A-Z]+\.\d+[A-Za-z]?\b")
_CONFLICT = re.compile(r"\bC\.\d{3}\b")
_DQ = re.compile(r"\bDQ\.\d{3}\b")

# Language that would signal an invented threshold, benchmark, or causal claim. Each is checked
# only OUTSIDE a refusal context -- a document saying "no materiality threshold exists" is
# correct, while one saying "flag changes above 5%" would be inventing one.
_INVENTION_PATTERNS = (
    (re.compile(r"\b(above|below|exceed(?:s|ing)?|greater than|less than)\s+\d+\s*%"),
     "an invented numeric threshold"),
    (re.compile(r"\bp\s*[<>=]\s*0?\.\d+"), "an invented statistical significance threshold"),
    (re.compile(r"\b(industry|market)\s+(average|benchmark|standard)\s+(is|of)\s+\d"),
     "an invented benchmark value"),
    (re.compile(r"\b(?<!not )caused by\b"), "an unhedged causal claim"),
)
# Phrases whose presence in the same line marks it as a REFUSAL of the thing, not an assertion.
_REFUSAL_MARKERS = ("not determinable", "no threshold", "never", "must not", "forbid", "refus",
                    "does not fix", "cannot", "would be inventing", "invented", "no benchmark",
                    "is not a", "without evidence", "no causal", "not a demonstrated")


def _read(path):
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return None
    with open(full, encoding="utf-8") as f:
        return f.read()


def check_symbols(registry, problems, warnings):
    """Checks 1 and 3: every symbol a Phase 7 artifact names must exist."""
    known_metrics = set(registry.all_ids())

    dq_ids = set()
    dq_path = os.path.join(ROOT, "data_quality_registry.csv")
    if os.path.exists(dq_path):
        with open(dq_path, encoding="utf-8") as f:
            dq_ids = {r["dq_id"] for r in csv.DictReader(f)}

    conflict_ids = set()
    for mid in registry.all_ids():
        conflict_ids.update(registry.get(mid).conflict_ids)
    conflicts_md = _read("conflicts.md") or ""
    conflict_ids.update(_CONFLICT.findall(conflicts_md))

    for doc in PHASE7_DOCS + PHASE7_REGISTRIES:
        text = _read(doc)
        if text is None:
            problems.append(f"{doc}: MISSING -- declared as a Phase 7 deliverable")
            continue
        for m in set(_METRIC.findall(text)):
            if m not in known_metrics:
                problems.append(
                    f"{doc}: names metric {m!r}, which is not in semantic_metric_registry.csv")
        for c in set(_CONFLICT.findall(text)):
            if conflict_ids and c not in conflict_ids:
                warnings.append(f"{doc}: names conflict {c!r} not found in conflicts.md")
        for d in set(_DQ.findall(text)):
            if dq_ids and d not in dq_ids:
                problems.append(
                    f"{doc}: names {d!r}, which is not in data_quality_registry.csv")


def check_dashboard(registry, gate, problems):
    """Checks 2 and 4: the dashboard's trust levels and headline permissions match the gate."""
    path = os.path.join(ROOT, "owner_dashboard_registry.csv")
    if not os.path.exists(path):
        problems.append("owner_dashboard_registry.csv: MISSING")
        return
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mid = row["metric_id"]
            if mid not in registry:
                problems.append(f"dashboard tile {mid!r} is not a registry metric")
                continue
            actual = gate.authorize(mid).effective_level
            if row["trust_level"] != actual:
                problems.append(
                    f"dashboard tile {mid}: claims trust {row['trust_level']}, gate says "
                    f"{actual} (ai_agent_roles.md 3: the gate's verdict is binding)")
            permitted = row["headline_permitted"] == "True"
            should = actual in ("SAFE", "DISCLOSE")
            if permitted != should:
                problems.append(
                    f"dashboard tile {mid}: headline_permitted={permitted} but trust is "
                    f"{actual}")
            if actual in ("SHOW_BOTH", "BLOCK"):
                if int(row["definition_count"] or 0) < 2:
                    problems.append(
                        f"dashboard tile {mid}: {actual} exposes "
                        f"{row['definition_count']} definition(s); a conflict cannot be read "
                        f"from fewer than 2")
                if not row["conflict_ids"] and actual == "BLOCK":
                    problems.append(f"dashboard tile {mid}: BLOCK names no conflict")
            if actual == "DISCLOSE" and not row["caveat"].strip():
                problems.append(f"dashboard tile {mid}: DISCLOSE with no caveat rendered")


def check_role_views(registry, gate, problems):
    """Check 5: no role view may permit a conclusion the trust policy forbids."""
    path = os.path.join(ROOT, "role_view_registry.csv")
    if not os.path.exists(path):
        problems.append("role_view_registry.csv: MISSING")
        return
    role_ids = {r.role_id for r in analyst_roles.all_roles()}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mid, rid = row["metric_id"], row["role_id"]
            if rid not in role_ids:
                problems.append(f"role view names unknown role {rid!r}")
                continue
            if mid not in registry:
                problems.append(f"role view names unknown metric {mid!r}")
                continue
            actual = gate.authorize(mid).effective_level
            if row["trust_level"] != actual:
                problems.append(
                    f"role view {rid}/{mid}: claims {row['trust_level']}, gate says {actual}")
            permitted = row["headline_permitted"] == "True"
            if permitted != (actual in ("SAFE", "DISCLOSE")):
                problems.append(
                    f"role view {rid}/{mid}: headline permission contradicts trust {actual}")
            if actual in ("SHOW_BOTH", "BLOCK"):
                concl = row["permitted_conclusion"].lower()
                if "may not select" not in concl and "may not state" not in concl:
                    problems.append(
                        f"role view {rid}/{mid}: {actual} conclusion does not forbid selecting "
                        f"a single definition")

            # Every role must see the SAME definition for the same metric.
            if row["metric_name"] != registry.get(mid).semantic_name:
                problems.append(
                    f"role view {rid}/{mid}: metric name differs from the registry -- role "
                    f"views must share one definition")


def check_conflict_visibility(registry, gate, problems):
    """Check 6: every conflicted metric must remain visible on every declared surface."""
    path = os.path.join(ROOT, "conflict_disclosure_registry.csv")
    if not os.path.exists(path):
        problems.append("conflict_disclosure_registry.csv: MISSING")
        return
    listed = set()
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            listed.add(row["metric_id"])
            if row["headline_permitted_anywhere"] != "False":
                problems.append(
                    f"conflict registry {row['metric_id']}: permits a headline somewhere")
            n_defs = int(row["competing_definitions"] or 0)
            computable = row.get("definitions_computable", "True") == "True"
            if n_defs < 2 and computable:
                problems.append(
                    f"conflict registry {row['metric_id']}: fewer than 2 definitions listed")
            if n_defs < 2 and not computable:
                # Legitimate: the conflict is real but its definitions are not computable in
                # the current engine. The registry must SAY so rather than imply two figures.
                if NOT_DET not in row.get("resolution_note", ""):
                    problems.append(
                        f"conflict registry {row['metric_id']}: has no computable definitions "
                        f"but does not state so with the exact required phrase")
            for surface in ("owner_dashboard", "role_views", "bi_cards", "executive_summary"):
                if surface not in row["must_appear_on"]:
                    problems.append(
                        f"conflict registry {row['metric_id']}: not required on {surface}")

    for mid in registry.all_ids():
        if gate.authorize(mid).effective_level in ("SHOW_BOTH", "BLOCK") and mid not in listed:
            problems.append(
                f"{mid} is {gate.authorize(mid).effective_level} but is absent from "
                f"conflict_disclosure_registry.csv -- a conflict that is not registered can be "
                f"dropped from a surface without anything noticing")


def check_capabilities(problems):
    """Check 7: every capability a Phase 7 doc names must be registered."""
    path = os.path.join(ROOT, "analysis_capability_registry.csv")
    if not os.path.exists(path):
        problems.append("analysis_capability_registry.csv: MISSING")
        return
    with open(path, encoding="utf-8") as f:
        known = {r["capability_id"] for r in csv.DictReader(f)}
    # Widget names are BI-contract vocabulary, not capabilities. They are validated against the
    # widgets the generated dashboard registry actually emits -- so a document naming a widget
    # the dashboard cannot render still fails, just against the right registry.
    widgets = set()
    dash = os.path.join(ROOT, "owner_dashboard_registry.csv")
    if os.path.exists(dash):
        with open(dash, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                widgets.add(row["widget"])
                widgets.add(row["render_directive"])

    text = " ".join(_read(d) or "" for d in PHASE7_DOCS)
    for cap in re.findall(r"`([a-z][a-z_]{5,})`", text):
        if cap in widgets:
            continue
        if cap.endswith("_analysis") or cap.endswith("_view") or cap.startswith("kpi_"):
            if cap not in known:
                problems.append(
                    f"a Phase 7 document names capability {cap!r}, which is in neither "
                    f"analysis_capability_registry.csv nor the dashboard widget vocabulary")


def check_phrase_and_inventions(problems, warnings):
    """Checks 8 and 9: the exact refusal phrase, and no invented thresholds or causal claims."""
    for doc in PHASE7_DOCS:
        text = _read(doc)
        if text is None:
            continue
        if "NOT_DETERMINABLE" in text and NOT_DET not in text:
            warnings.append(
                f"{doc}: discusses NOT_DETERMINABLE without quoting the exact required phrase")

        for line in text.splitlines():
            low = line.lower()
            if any(mark in low for mark in _REFUSAL_MARKERS):
                continue          # the line REFUSES the thing rather than asserting it
            if line.strip().startswith(("|", ">")) and "refus" in low:
                continue
            for pattern, what in _INVENTION_PATTERNS:
                if pattern.search(line):
                    problems.append(f"{doc}: {what} -- {line.strip()[:120]}")


def check_foundation_untouched(problems):
    """Phase 7 is a specification phase: it must not have altered the Phase 1-6 foundation."""
    from engine.semantic_registry import cross_check_against_legacy_registry
    drift = cross_check_against_legacy_registry(SemanticRegistry())
    for d in drift:
        problems.append(f"semantic registry drift: {d}")

    manifest = os.path.join(ROOT, "evidence", "file_manifest.csv")
    if os.path.exists(manifest):
        import hashlib
        h = hashlib.sha256()
        with open(manifest, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            p = os.path.join(ROOT, r["file"])
            if not os.path.exists(p):
                problems.append(f"source CSV missing: {r['file']}")
                continue
            with open(p, "rb") as fh:
                h.update(fh.read())
        digest = h.hexdigest()
        expected = "aed87d5270eca59723a4380dc0c2f020a6931a8437bff5bd2b86e44809076f26"
        if digest != expected:
            problems.append(
                f"SOURCE CSVs CHANGED: combined SHA-256 {digest} != baseline {expected}")
        return digest
    return ""


def main():
    registry = SemanticRegistry()
    gate = TrustGate(registry)
    problems, warnings = [], []

    check_symbols(registry, problems, warnings)
    check_dashboard(registry, gate, problems)
    check_role_views(registry, gate, problems)
    check_conflict_visibility(registry, gate, problems)
    check_capabilities(problems)
    check_phrase_and_inventions(problems, warnings)
    digest = check_foundation_untouched(problems)

    present = [d for d in PHASE7_DOCS if _read(d) is not None]

    print("=" * 88)
    print("PHASE 7 CONSISTENCY VALIDATION -- blueprint vs. the live Phase 1-6 system")
    print("=" * 88)
    print(f"\n[deliverables]      {len(present)}/{len(PHASE7_DOCS)} documents present")
    print(f"[registries]        {sum(1 for r in PHASE7_REGISTRIES if _read(r) is not None)}"
          f"/{len(PHASE7_REGISTRIES)} present")
    print(f"[metrics]           {len(registry.all_ids())} in the semantic registry")
    print(f"[roles]             {len(analyst_roles.ALL_ROLES)}")
    print(f"[source integrity]  SHA-256 {digest[:16]}... "
          f"{'MATCHES baseline' if not any('SOURCE CSVs' in p for p in problems) else 'CHANGED'}")

    print(f"\n[problems]          {len(problems)}")
    print(f"[warnings]          {len(warnings)}")

    if problems:
        print("\nINCONSISTENCIES (each names the artifact and the rule):")
        for p in problems:
            print(f"   {p}")
    else:
        print("\nNo inconsistency between the Phase 7 blueprint and the Phase 1-6 system.")

    if warnings:
        print("\nWarnings (non-blocking):")
        for w in warnings:
            print(f"   {w}")

    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
