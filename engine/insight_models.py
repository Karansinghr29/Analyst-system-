"""
insight_models.py -- Phase 5. Structures for proactive insights and decision support.

Contains NO business content and NO thresholds. Every field is populated at runtime from the
already-completed evidence layer (data_quality_registry.csv, semantic_metric_registry.csv,
conflicts.md's ids, validation_summary.csv). insight_generation_spec.md 2 is explicit that
inventing a trigger not grounded in the semantic layer "would itself be a
hallucination-prevention violation"; the same applies to inventing a threshold or a score.

The one design decision worth stating up front: there is no blended importance score anywhere in
this module. insight_generation_spec.md 4 forbids it -- "not a blended numeric score (a blended
score would itself be an invented metric, the same failure mode analytics_execution_spec.md 2.8
already prohibits for risk-scan composites)" -- so ranking dimensions are carried separately and
compared lexicographically.
"""
from dataclasses import dataclass, field

NOT_DETERMINABLE_TEXT = "Not determinable from exported evidence."


# --- Triggers (insight_generation_spec.md 2) ---------------------------------------------------
# "no other trigger source is in scope"

TRIGGER_DQ_SEVERITY = "dq_severity"            # 2 condition 1
TRIGGER_ANOMALY = "anomaly_outside_history"    # 2 condition 2
TRIGGER_MATERIAL_DELTA = "material_delta"      # 2 condition 3
TRIGGER_RISK_BOUNDARY = "risk_boundary"        # 2 condition 4
TRIGGER_DEFINITION_CONFLICT = "definition_conflict"   # 5, BLOCK-conflict insights

ALL_TRIGGERS = (TRIGGER_DQ_SEVERITY, TRIGGER_ANOMALY, TRIGGER_MATERIAL_DELTA,
                TRIGGER_RISK_BOUNDARY, TRIGGER_DEFINITION_CONFLICT)

# Triggers whose firing condition the specifications DELIBERATELY leave open. These are not
# oversights in this implementation -- the specs say so in their own words, quoted here so the
# reason travels with the code:
UNSPECIFIED_TRIGGERS = {
    TRIGGER_ANOMALY: (
        "analytics_execution_spec.md 2.5: 'the specific statistical method is an "
        "implementation-phase decision, not fixed by this specification'. No anomaly threshold "
        "exists in the exported evidence or in any specification document, so no anomaly "
        "trigger can fire without inventing one. " + NOT_DETERMINABLE_TEXT),
    TRIGGER_MATERIAL_DELTA: (
        "insight_generation_spec.md 2 condition 3: 'this specification does not fix the "
        "threshold value (an implementation-phase/business decision)'. No materiality threshold "
        "exists in the exported evidence, so no period-comparison trigger can fire without "
        "inventing one. " + NOT_DETERMINABLE_TEXT),
}


# --- Insight classes, mapped to business_insight_framework.md Part A ---------------------------
# These are LABELS for categories Part A already defines; they introduce no new analysis.

CLASS_MATERIAL_FINANCIAL_CHANGE = "material_financial_change"
CLASS_REVENUE_COLLECTION = "revenue_collection_deterioration"
CLASS_EXPENSE_ANOMALY = "expense_anomaly"
CLASS_RECEIVABLES_RISK = "receivables_risk"
CLASS_DEPOSIT_RISK = "deposit_risk"
CLASS_OCCUPANCY_CHANGE = "occupancy_change"
CLASS_MAINTENANCE_RISK = "maintenance_risk"
CLASS_EB_ISSUE = "eb_electricity_issue"
CLASS_ACCOUNTING_DQ_RISK = "accounting_data_quality_risk"
CLASS_DEFINITION_CONFLICT = "business_definition_conflict"

ALL_CLASSES = (CLASS_MATERIAL_FINANCIAL_CHANGE, CLASS_REVENUE_COLLECTION, CLASS_EXPENSE_ANOMALY,
               CLASS_RECEIVABLES_RISK, CLASS_DEPOSIT_RISK, CLASS_OCCUPANCY_CHANGE,
               CLASS_MAINTENANCE_RISK, CLASS_EB_ISSUE, CLASS_ACCOUNTING_DQ_RISK,
               CLASS_DEFINITION_CONFLICT)

# Business area -> insight class. Derived from data_quality_registry.csv's own `business_area`
# column and business_insight_framework.md Part A's category tables. An area with no mapping
# falls back to the accounting/DQ class rather than being dropped.
AREA_TO_CLASS = (
    ("invoice", CLASS_RECEIVABLES_RISK),
    ("ar ", CLASS_RECEIVABLES_RISK),
    ("tenant dues", CLASS_RECEIVABLES_RISK),
    ("receivable", CLASS_RECEIVABLES_RISK),
    ("deposit", CLASS_DEPOSIT_RISK),
    ("occupancy", CLASS_OCCUPANCY_CHANGE),
    ("maintenance", CLASS_MAINTENANCE_RISK),
    ("eb", CLASS_EB_ISSUE),
    ("electricity", CLASS_EB_ISSUE),
    ("expense", CLASS_EXPENSE_ANOMALY),
    ("p&l", CLASS_EXPENSE_ANOMALY),
    ("profit", CLASS_MATERIAL_FINANCIAL_CHANGE),
    ("owner", CLASS_MATERIAL_FINANCIAL_CHANGE),
    ("collection", CLASS_REVENUE_COLLECTION),
    ("revenue", CLASS_REVENUE_COLLECTION),
    ("ledger", CLASS_ACCOUNTING_DQ_RISK),
)


def classify_area(business_area):
    a = (business_area or "").lower()
    for needle, cls in AREA_TO_CLASS:
        if needle in a:
            return cls
    return CLASS_ACCOUNTING_DQ_RISK


# --- The insight object -------------------------------------------------------------------------

@dataclass(frozen=True)
class RankingDimensions:
    """insight_generation_spec.md 4's four ordered dimensions, kept SEPARATE. There is
    deliberately no combined score field -- see the module docstring."""
    trust_adjusted_severity: int = 0   # 1: lower is more urgent
    recency: int = 0                   # 2: lower is more recently true
    materiality_amount: object = None  # 3: Rs. amount, or None when not determinable
    materiality_note: str = ""
    coverage_sufficient: bool = True   # 4: False for maintenance/EB trend framing

    def sort_key(self):
        """Lexicographic over the documented ordering. A missing materiality sorts last within
        its tier rather than being treated as zero -- absence of a figure is not smallness."""
        amt = self.materiality_amount
        return (
            self.trust_adjusted_severity,
            self.recency,
            -(amt if isinstance(amt, (int, float)) else -1),
            0 if self.coverage_sufficient else 1,
        )


@dataclass(frozen=True)
class Insight:
    """One proactive insight. insight_generation_spec.md 1: 'an insight is not a different KIND
    of output, it is an answer the system generated without being asked, and it must satisfy
    every requirement a reactive answer does.'"""
    insight_id: str
    insight_class: str
    trigger: str
    trigger_metric_ids: tuple

    # The reasoning ladder (business_reasoning_spec.md). Stages that do not apply stay empty --
    # Part B: "A stage may be skipped only if it genuinely does not apply ... it may never be
    # skipped because the evidence for it is inconvenient."
    fact: str = ""
    calculation: str = ""
    observation: str = ""
    inference: str = ""
    hypothesis: str = ""
    recommendation: str = ""

    trust_level: str = ""
    confidence: str = ""
    caveat: str = ""
    conflict_ids: tuple = ()
    dq_ids: tuple = ()
    evidence_sources: tuple = ()
    time_period: str = ""
    business_dimension: str = ""
    affected_amount: object = None
    affected_count: object = None
    limitations: str = ""
    ranking: RankingDimensions = field(default_factory=RankingDimensions)
    headline_permitted: bool = False

    @property
    def reached_observation(self):
        """insight_generation_spec.md 3: 'A candidate must reach at minimum the OBSERVATION
        stage -- a bare FACT/CALCULATION is not yet an insight.'"""
        return bool(self.observation.strip())

    def stages(self):
        out = []
        for name, text in (("FACT", self.fact), ("CALCULATION", self.calculation),
                           ("OBSERVATION", self.observation), ("INFERENCE", self.inference),
                           ("HYPOTHESIS", self.hypothesis),
                           ("RECOMMENDATION", self.recommendation)):
            if text.strip():
                out.append((name, text))
        return tuple(out)


# --- Decision support (Phase 5 objective 6) -------------------------------------------------------

@dataclass
class DecisionSupport:
    """The structured answer a business decision-maker consumes. Sections are populated ONLY
    where evidence permits -- the brief is explicit: 'Do not manufacture missing sections.'
    An empty section means the evidence did not support one, and `omitted_sections` records
    why, so absence is visible rather than silent."""
    question: str = ""
    executive_summary: str = ""
    key_numbers: tuple = ()          # (label, value, metric_id, trust_level)
    trend_comparison: tuple = ()
    drivers: tuple = ()
    risks: tuple = ()
    data_quality_warnings: tuple = ()
    definition_conflicts: tuple = ()
    recommended_actions: tuple = ()
    evidence: tuple = ()
    confidence: str = ""
    limitations: tuple = ()
    trust_level: str = ""
    headline_permitted: bool = False
    omitted_sections: dict = field(default_factory=dict)

    def populated_sections(self):
        return tuple(name for name in (
            "executive_summary", "key_numbers", "trend_comparison", "drivers", "risks",
            "data_quality_warnings", "definition_conflicts", "recommended_actions",
            "evidence", "limitations") if getattr(self, name))
