"""
result.py -- the structured, machine-readable result contract (analytics_execution_spec.md +
answer_contract.md). NOT a chat response -- an internal object for later AI-layer consumption.

Two shapes:
  MetricResult        -- one computed definition's value + full provenance (SAFE/DISCLOSE, or
                          one labelled member of a SHOW_BOTH family, or the internal value
                          behind a BLOCK verdict).
  MetricAnswer        -- what execution.py actually returns for a metric_id: wraps ONE
                          MetricResult (SAFE/DISCLOSE), MULTIPLE labelled MetricResults
                          (SHOW_BOTH), a blocked-with-explanation payload (BLOCK), or a
                          not-determinable payload (NOT_DETERMINABLE). The trust_level on
                          MetricAnswer is always authoritative for how a caller may use `results`.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


NOT_DETERMINABLE_TEXT = "Not determinable from exported evidence."


@dataclass
class MetricResult:
    """One computed number/series with full provenance -- the unit SHOW_BOTH answers are built
    from (never merged, always kept as separate MetricResult objects)."""
    metric_id: str
    metric_name: str
    definition_label: str          # e.g. "Definition A", "Def A: v_outstanding_receivables"
    value: object                  # scalar, dict (grouped), or None
    unit: str
    period: str
    grain: str
    dimensions: str
    date_field: str
    filters_applied: str
    reversal_policy_applied: str
    soft_delete_policy_applied: str
    evidence_sources: tuple
    calculation_provenance: str
    validation_status: str         # MATCH | DIFFERS | NOT_DETERMINABLE | UNVERIFIED
    validation_reference: str
    validation_detail: Optional[dict] = None   # {reconstructed, reference, abs_diff, pct_diff}
    limitations: str = ""
    computed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # --- Phase 2: answer_contract.md structural fields -------------------------------------
    confidence: str = ""               # answer_contract.md 3 label for THIS definition
    confidence_basis: str = ""
    citations: tuple = field(default_factory=tuple)   # citation.Citation, the 4-layer chain
    as_of: str = ""                    # business date basis actually used (contract 1)
    sanity_checks: tuple = field(default_factory=tuple)   # validator.SanityCheck results

    def contract_identity(self):
        """Everything about this result EXCEPT its wall-clock stamp. answer_contract.md 6
        requires 're-asking an identical resolved query must produce an identical answer
        object' for SAFE metrics; `computed_at` is by definition different on every call, so
        determinism is asserted over this projection rather than over the raw dataclass."""
        return (self.metric_id, self.definition_label, repr(self.value), self.unit,
                self.grain, self.date_field, self.filters_applied,
                self.reversal_policy_applied, self.soft_delete_policy_applied,
                tuple(self.evidence_sources), self.validation_status, self.confidence)


@dataclass
class MetricAnswer:
    """Top-level engine output for one resolved metric_id. `results` shape depends on
    trust_level:
      SAFE / DISCLOSE          -> exactly one MetricResult
      SHOW_BOTH                -> 2+ MetricResults, each separately labelled, NEVER merged
      BLOCK                    -> 0+ internal MetricResults (for disclosure only) + `blocked=True`
      NOT_DETERMINABLE         -> empty results, `not_determinable_reason` populated
    """
    metric_id: str
    metric_name: str
    trust_level: str
    ai_handling: str
    caveat: str
    conflict_ids: tuple
    dq_ids: tuple
    results: tuple = field(default_factory=tuple)   # tuple[MetricResult, ...]
    blocked: bool = False
    blocked_reason: str = ""
    not_determinable_reason: str = ""
    dependency_metrics: tuple = field(default_factory=tuple)
    numeric_difference: Optional[dict] = None   # for SHOW_BOTH: pairwise diffs between results

    # --- Phase 2: answer_contract.md structural fields -------------------------------------
    confidence: str = ""                  # contract 3; SPLIT for SHOW_BOTH, BLOCKED for BLOCK
    confidence_basis: str = ""
    epistemic_label: str = "CALCULATION"  # Phase 2 ceiling; the ladder above it is Phase 3
    as_of: str = ""
    follow_up: tuple = field(default_factory=tuple)
    headline_permitted: bool = False      # set by the gate, never by a calculator
    propagation_justification: str = ""   # metric_dependency_graph.md 6 audit trail
    trust_sources: Optional[dict] = None  # {own, dependency, documented_floor}
    contract_violations: tuple = field(default_factory=tuple)

    @property
    def headline(self):
        """The ONLY sanctioned way to read a single number off an answer. Returns None whenever
        the gate withheld headline permission (SHOW_BOTH / BLOCK / NOT_DETERMINABLE), so a
        caller cannot obtain a misleading scalar even by accident. answer_contract.md 5:
        'BLOCK: value field is absent or explicitly null for the headline figure.'"""
        if not self.headline_permitted:
            return None
        return self.results[0].value if self.results else None

    def contract_identity(self):
        """Determinism projection -- see MetricResult.contract_identity."""
        return (self.metric_id, self.trust_level, self.confidence, self.blocked,
                self.not_determinable_reason, tuple(self.conflict_ids), tuple(self.dq_ids),
                tuple(r.contract_identity() for r in self.results))

    def headline_text(self):
        """The ONE thing every caller must respect: SHOW_BOTH/BLOCK never expose a single
        headline number. This helper enforces that at the object level, not just by convention."""
        if self.trust_level == "NOT_DETERMINABLE":
            return NOT_DETERMINABLE_TEXT
        if self.trust_level == "BLOCK":
            return (f"BLOCKED: {self.metric_name} has conflicting definitions "
                    f"({', '.join(self.conflict_ids)}) and no single number may be stated. "
                    f"{self.blocked_reason}")
        if self.trust_level == "SHOW_BOTH":
            parts = [f"{r.definition_label}: {r.value}" for r in self.results]
            return " | ".join(parts)
        if len(self.results) == 1:
            return str(self.results[0].value)
        if len(self.results) > 1:
            # SAFE/DISCLOSE metrics can legitimately carry multiple COMPLEMENTARY (not
            # competing) sub-views -- e.g. M.TB.001's two trial-balance conventions, both
            # proven exact, neither one a "conflicting definition." This is NOT the
            # SHOW_BOTH case (no conflict_ids drive it) -- format identically for
            # transparency, but the trust_level itself remains the authoritative signal.
            parts = [f"{r.definition_label}: {r.value}" for r in self.results]
            return " | ".join(parts)
        raise AssertionError(f"{self.metric_id}: trust_level={self.trust_level} but "
                              f"results is empty and not flagged BLOCK/NOT_DETERMINABLE")
