"""
propagation.py -- machine-readable encoding of `metric_dependency_graph.md` 6's
DQ/conflict -> trust-level propagation table, plus that section's closing paragraph of
**explicitly NOT asserted** dependencies.

Why this module exists (Phase 2, per implementation_roadmap.md):
Phase 1's trust_gate.py propagated trust only along `semantic_metric_registry.csv`'s
`dependency_metrics` column (metric -> metric edges). That is necessary but NOT sufficient:
metric_dependency_graph.md 6 is a *different* relation -- DQ/conflict finding -> metric -- and
it is the auditable justification for why each metric carries the trust level it carries.
ai_evaluation_framework.md 1.3 requires that relation be tested in BOTH directions:

  - a documented downgrade that is MISSING is a defect (false negative), and
  - a downgrade applied where the graph explicitly says none should be is EQUALLY a defect
    ("A false-positive downgrade (over-cautious, marking a genuinely SAFE metric as DISCLOSE)
    is also a defect, not merely a false negative -- both directions must be tested.")

The critical design consequence: **carrying a conflict_id or dq_id does NOT by itself imply a
downgrade.** Several metrics correctly stay SAFE while carrying one (M.LIFE.004 carries C.001;
M.MAINT.002 carries C.023; M.TEN.001 carries DQ.003; M.TB.001 carries C.002). An implementation
that downgraded on the mere presence of an id would fail 1.3. This table -- not the id lists --
is the authority.

This module reads the semantic layer; it never computes a business value and never writes.
"""
from dataclasses import dataclass, field

from engine.semantic_registry import SemanticRegistry

# Sentinel for rows where metric_dependency_graph.md 6 documents that a downgrade occurs but
# does not fix the exact resulting level for that particular metric (it names the level for
# some members of the row and not others). Asserting "worse than SAFE" is the strongest claim
# the evidence supports -- inventing an exact level here would be fabrication.
NOT_SAFE = "__NOT_SAFE__"

_SEVERITY = {"SAFE": 0, "DISCLOSE": 1, "SHOW_BOTH": 2, "NOT_DETERMINABLE": 3, "BLOCK": 4}


@dataclass(frozen=True)
class PropagationRule:
    """One row of metric_dependency_graph.md 6."""
    upstream_ids: tuple          # the DQ/conflict ids this row is about
    severity: str                # CRITICAL / HIGH / MEDIUM, verbatim from the table
    downgrades: dict             # metric_id -> exact expected trust level, or NOT_SAFE
    preserved: tuple             # metric_ids the row explicitly says are NOT downgraded
    note: str                    # the row's own justification text, condensed but faithful


@dataclass(frozen=True)
class NonDependency:
    """One assertion from 6's closing 'No false dependency was created' paragraph."""
    upstream_id: str
    metric_ids: tuple
    expected_trust: str          # what these metrics must REMAIN
    evidence: str                # the proof the graph cites for why no edge exists


# ---------------------------------------------------------------------------------------------
# metric_dependency_graph.md 6 -- the propagation table, row by row, in document order.
# ---------------------------------------------------------------------------------------------

PROPAGATION_TABLE = (
    PropagationRule(
        upstream_ids=("DQ.002", "C.001", "C.005"),
        severity="CRITICAL",
        downgrades={
            "M.AR.001A": "SHOW_BOTH", "M.AR.001B": "SHOW_BOTH",
            "M.AR.001C": "BLOCK", "M.AR.001D": "BLOCK",
            "M.AR.002": NOT_SAFE, "M.AR.003": NOT_SAFE, "M.RISK.001": NOT_SAFE,
        },
        preserved=("M.LIFE.004",),
        note="4-way AR conflict. M.LIFE.004 stays SAFE (single-convention use, disclosed).",
    ),
    PropagationRule(
        upstream_ids=("DQ.019", "C.003"),
        severity="CRITICAL",
        downgrades={"M.AR.001D": "BLOCK"},
        preserved=(),
        note="tenant_transactions frozen; BLOCK for catastrophic ~120x misuse risk.",
    ),
    PropagationRule(
        upstream_ids=("DQ.016", "C.010", "C.011"),
        severity="CRITICAL",
        downgrades={"M.OWN.002": "SHOW_BOTH", "M.PROFIT.001": "BLOCK"},
        preserved=(),
        note="Owner-rent omission in get_universal_metrics v1.",
    ),
    PropagationRule(
        upstream_ids=("DQ.001",),
        severity="CRITICAL",
        downgrades={"M.INV.001": "DISCLOSE"},
        preserved=(),
        note="Invoice internal drift (42.7%); individual-invoice trust only, aggregate total "
             "unaffected.",
    ),
    PropagationRule(
        upstream_ids=("DQ.004", "DQ.005", "C.006", "C.007", "C.008", "C.009"),
        severity="HIGH",
        downgrades={"M.OCC.001": "SHOW_BOTH", "M.OCC.002": "SHOW_BOTH", "M.OCC.005": "SHOW_BOTH"},
        preserved=("M.TEN.001", "M.TEN.002", "M.TEN.003"),
        note="Occupancy family. Raw status counts keep SAFE -- they use the unambiguous enum "
             "count, not an occupancy-% formula.",
    ),
    PropagationRule(
        upstream_ids=("DQ.015", "C.012", "C.013"),
        severity="HIGH",
        downgrades={"M.EXP.002": "DISCLOSE"},
        preserved=("M.EXP.001",),
        note="P&L bucket gap. M.EXP.001 (the total) is proven unaffected.",
    ),
    PropagationRule(
        upstream_ids=("DQ.028",),
        severity="HIGH",
        downgrades={"M.EB.001": "DISCLOSE", "M.EB.002": "DISCLOSE"},
        preserved=(),
        note="EB billing_month format.",
    ),
    PropagationRule(
        upstream_ids=("DQ.030", "C.021"),
        severity="HIGH",
        downgrades={},
        preserved=(),
        note="Wrong account_code in get_universal_metrics_series.collections. No registry metric "
             "exposes it; this is a pre-emptive guard rail against future addition, not a "
             "downgrade of anything currently present.",
    ),
    PropagationRule(
        upstream_ids=("DQ.008", "C.016"),
        severity="HIGH",
        downgrades={"M.DEP.002": "DISCLOSE", "M.DEP.003": "DISCLOSE"},
        preserved=(),
        note="Deposit settlement 2x pattern.",
    ),
    PropagationRule(
        upstream_ids=("DQ.006", "C.014", "DQ.007", "C.015"),
        severity="MEDIUM",
        downgrades={"M.COL.003": "DISCLOSE", "M.INV.001": "DISCLOSE"},
        preserved=(),
        note="Receipt/invoice ledger drift; ledger cross-check only, not the source totals.",
    ),
    PropagationRule(
        upstream_ids=("DQ.013", "C.020"),
        severity="HIGH",
        downgrades={
            "M.INV.001": "DISCLOSE", "M.INV.002": "DISCLOSE", "M.RISK.005": "DISCLOSE",
            "M.PROFIT.001": "BLOCK",
        },
        preserved=(),
        note="Duplicate invoices with no dedup mechanism; transitively reaches M.PROFIT.001 "
             "Def B.",
    ),
    PropagationRule(
        upstream_ids=("DQ.011", "DQ.012"),
        severity="HIGH/MEDIUM",
        downgrades={"M.RISK.003": "DISCLOSE", "M.RISK.004": "DISCLOSE"},
        preserved=("M.DEP.001",),
        note="Deposit risk. M.DEP.001 NOT downgraded -- the balance total is exact.",
    ),
    PropagationRule(
        upstream_ids=("DQ.003",),
        severity="MEDIUM",
        downgrades={"M.RISK.007": "DISCLOSE"},
        preserved=("M.OCC.001", "M.OCC.002", "M.OCC.003", "M.OCC.004", "M.OCC.005"),
        note="Overlapping allotments. No downgrade to the EXISTS-based occupancy snapshot "
             "metrics -- proven immaterial (H.013 shows 0 Staying/On-Notice overlap). NOTE: "
             "'preserved' here means 'DQ.003 contributes no downgrade'; the occupancy metrics "
             "are independently SHOW_BOTH via DQ.004/DQ.005, which is a different edge.",
    ),
    PropagationRule(
        upstream_ids=("DQ.018", "C.019"),
        severity="MEDIUM",
        downgrades={"M.RISK.002": "DISCLOSE"},
        preserved=(),
        note="Aging snapshot dependence -- a reproducibility hazard, not a value conflict.",
    ),
    PropagationRule(
        upstream_ids=("DQ.026",),
        severity="MEDIUM",
        downgrades={},
        preserved=(),
        note="Polymorphic orphan coverage gap. Caveat only, NOT a status change -- attaches to "
             "any metric relying on journal_entries.source_id for owner_payments / "
             "tenant_adjustments / assets / asset_payments / eb_payments.",
    ),
)


# ---------------------------------------------------------------------------------------------
# metric_dependency_graph.md 6 closing paragraph -- "No false dependency was created."
# These are the false-positive-downgrade guards required by ai_evaluation_framework.md 1.3.
# ---------------------------------------------------------------------------------------------

EXPLICIT_NON_DEPENDENCIES = (
    NonDependency(
        upstream_id="DQ.003",
        metric_ids=("M.TEN.001", "M.TEN.002"),
        expected_trust="SAFE",
        evidence="H.013 proves 0 overlap specifically for the Staying and On-Notice statuses.",
    ),
    NonDependency(
        upstream_id="DQ.028",
        metric_ids=("M.PROFIT.001",),
        # M.PROFIT.001 is BLOCK for an unrelated reason (DQ.016/C.010/C.011). The assertion the
        # graph makes is that DQ.028 contributes NOTHING to it -- tested via `contributes()`
        # below, not by asserting M.PROFIT.001's final level.
        expected_trust="__NO_CONTRIBUTION__",
        evidence="No evidence connects EB's billing_month format to the ledger total or "
                 "category-bucket reconstruction, which use entry_date throughout.",
    ),
    NonDependency(
        upstream_id="DQ.028",
        metric_ids=("M.EXP.001", "M.EXP.002"),
        expected_trust="__NO_CONTRIBUTION__",
        evidence="Same: EB billing_month format does not reach the ledger-derived expense "
                 "reconstruction.",
    ),
    NonDependency(
        upstream_id="C.023",
        metric_ids=("M.MAINT.001", "M.MAINT.002"),
        expected_trust="SAFE",
        evidence="Checked and disproven for this dataset -- both maintenance-cost paths agree "
                 "exactly. Documented as a structural risk, not an active discrepancy.",
    ),
)


# ---------------------------------------------------------------------------------------------
# Declared divergences: cases where two completed specification documents imply DIFFERENT trust
# levels for the same metric. These are NOT resolved here. The engine takes the stricter of the
# two (never the looser -- a loosening would be exactly the failure mode this project exists to
# prevent), and records the divergence so the Phase 2 report can raise it for an owner decision
# instead of a CSV edit quietly settling it.
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class TrustDivergence:
    metric_id: str
    registry_level: str      # semantic_metric_registry.csv
    implied_level: str       # what the other document(s) imply
    applied_level: str       # what the engine actually applies (always the stricter)
    evidence: str


DECLARED_TRUST_DIVERGENCES = (
    TrustDivergence(
        metric_id="M.AR.002",
        registry_level="SHOW_BOTH",
        implied_level="BLOCK",
        applied_level="BLOCK",
        evidence=(
            "semantic_metric_registry.csv assigns M.AR.002 ('Tenant dues by tenant') SHOW_BOTH. "
            "Two other completed documents imply BLOCK: (1) metric_dependency_graph.md 7 -- "
            "'EVERY composite KPI inherits the WORST trust level of its inputs' -- and "
            "M.AR.002's own dependency_metrics are M.AR.001A/B (SHOW_BOTH) and M.AR.001C/D "
            "(BLOCK); (2) ai_trust_policy.md 3 answers the question this metric IS -- 'How much "
            "does this tenant owe?' -> 'M.AR.001A-D (BLOCK ...). Never state one figure.' "
            "ai_evaluation_framework.md 3's scenario table agrees (BLOCK, all 4 AR definitions, "
            "~120x spread named). The engine applies BLOCK, the stricter posture. This is "
            "surfaced for an owner decision, not silently resolved in either direction."),
    ),
)


def declared_divergence(metric_id):
    for d in DECLARED_TRUST_DIVERGENCES:
        if d.metric_id == metric_id:
            return d
    return None


def _rules_touching(metric_id):
    return [r for r in PROPAGATION_TABLE if metric_id in r.downgrades]


def documented_floor(metric_id):
    """The worst trust level metric_dependency_graph.md 6 documents for this metric, or None if
    6 documents no downgrade for it at all. NOT_SAFE rows contribute 'at least DISCLOSE'."""
    worst = None
    for rule in _rules_touching(metric_id):
        level = rule.downgrades[metric_id]
        if level == NOT_SAFE:
            level = "DISCLOSE"   # weakest level that still satisfies "downgraded from SAFE"
        if worst is None or _SEVERITY[level] > _SEVERITY[worst]:
            worst = level
    return worst


def contributes(upstream_id, metric_id):
    """Does metric_dependency_graph.md 6 assert an edge from this DQ/conflict id to this
    metric? Used to test the EXPLICIT_NON_DEPENDENCIES in the direction the graph states them
    (no contribution), independently of the metric's final level."""
    for rule in PROPAGATION_TABLE:
        if upstream_id in rule.upstream_ids and metric_id in rule.downgrades:
            return True
    return False


def justification(metric_id):
    """Human-readable audit trail: which 6 rows (if any) explain this metric's trust level.
    Returned as part of the Answer Contract's conflict/DQ disclosure so a reviewer can trace a
    trust posture back to its documented cause rather than taking the CSV column on faith."""
    rules = _rules_touching(metric_id)
    if not rules:
        return ("No metric_dependency_graph.md 6 propagation row downgrades this metric; its "
                "trust level is intrinsic to its own definition.")
    return " | ".join(
        f"[{'/'.join(r.upstream_ids)} ({r.severity})] -> "
        f"{'at least DISCLOSE' if r.downgrades[metric_id] == NOT_SAFE else r.downgrades[metric_id]}"
        f": {r.note}"
        for r in rules
    )


@dataclass
class PropagationAudit:
    missing_downgrades: list = field(default_factory=list)      # false negatives
    false_downgrades: list = field(default_factory=list)        # false positives
    unknown_metric_ids: list = field(default_factory=list)      # table names a nonexistent id

    @property
    def clean(self):
        return not (self.missing_downgrades or self.false_downgrades or self.unknown_metric_ids)

    def summary(self):
        if self.clean:
            return ("metric_dependency_graph.md 6 propagation audit: CLEAN "
                    "(0 missing downgrades, 0 false downgrades).")
        return (f"PROPAGATION AUDIT FAILED -- missing={len(self.missing_downgrades)}, "
                f"false={len(self.false_downgrades)}, unknown={len(self.unknown_metric_ids)}")


def audit(registry: SemanticRegistry) -> PropagationAudit:
    """ai_evaluation_framework.md 1.3, both directions, over the whole table.

    Direction 1 (false negative): every metric the table downgrades must actually carry at
      least the documented level in semantic_metric_registry.csv.
    Direction 2 (false positive): every metric a row explicitly PRESERVES must not have been
      pushed below SAFE *by that row*. Because a metric can be legitimately downgraded by a
      DIFFERENT row (M.OCC.001 is preserved w.r.t. DQ.003 but is SHOW_BOTH via DQ.004/DQ.005),
      a preserved metric is only a false positive if NO other row downgrades it and it is
      nonetheless non-SAFE.
    """
    result = PropagationAudit()

    for rule in PROPAGATION_TABLE:
        for mid, expected in rule.downgrades.items():
            if mid not in registry:
                result.unknown_metric_ids.append(
                    f"{'/'.join(rule.upstream_ids)}: downgrades unknown metric_id {mid!r}")
                continue
            actual = registry.get(mid).trust_level
            if expected == NOT_SAFE:
                if actual == "SAFE":
                    result.missing_downgrades.append(
                        f"{mid}: {'/'.join(rule.upstream_ids)} documents a downgrade, but the "
                        f"registry has it SAFE.")
            elif _SEVERITY[actual] < _SEVERITY[expected]:
                result.missing_downgrades.append(
                    f"{mid}: {'/'.join(rule.upstream_ids)} documents {expected}, registry has "
                    f"{actual} (weaker than documented).")

        for mid in rule.preserved:
            if mid not in registry:
                result.unknown_metric_ids.append(
                    f"{'/'.join(rule.upstream_ids)}: preserves unknown metric_id {mid!r}")
                continue
            actual = registry.get(mid).trust_level
            if actual == "SAFE":
                continue
            if actual == "NOT_DETERMINABLE":
                # NOT_DETERMINABLE is NOT a conflict-driven downgrade -- it is a
                # validation-COVERAGE statement ("No exported reference exists to validate this
                # metric", verbatim from these metrics' own caveat_text, status
                # ACTIVE_UNVERIFIED). metric_dependency_graph.md 6's table governs downgrades
                # caused by DQ/conflict findings only, so a NOT_DETERMINABLE metric named in a
                # `preserved` list (M.OCC.003/M.OCC.004 under DQ.003) is not evidence of a
                # false-positive downgrade. Treating it as one would flag a defect that the
                # semantic layer does not actually contain.
                continue
            if documented_floor(mid) is None:
                result.false_downgrades.append(
                    f"{mid}: metric_dependency_graph.md 6 explicitly preserves this metric "
                    f"w.r.t. {'/'.join(rule.upstream_ids)} and no other row downgrades it, yet "
                    f"the registry has it {actual}.")

    for nd in EXPLICIT_NON_DEPENDENCIES:
        for mid in nd.metric_ids:
            if mid not in registry:
                result.unknown_metric_ids.append(
                    f"non-dependency {nd.upstream_id}: unknown metric_id {mid!r}")
                continue
            if contributes(nd.upstream_id, mid):
                result.false_downgrades.append(
                    f"{mid}: {nd.upstream_id} is an EXPLICIT non-dependency "
                    f"({nd.evidence}) but the propagation table asserts an edge.")
            if nd.expected_trust not in ("__NO_CONTRIBUTION__",):
                actual = registry.get(mid).trust_level
                if actual != nd.expected_trust:
                    result.false_downgrades.append(
                        f"{mid}: must remain {nd.expected_trust} ({nd.upstream_id} is an "
                        f"explicit non-dependency -- {nd.evidence}) but registry has {actual}.")

    return result
