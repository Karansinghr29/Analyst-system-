"""
validation.py -- compares an Execution result against validation_summary.csv's already-proven
reference values (Phase E). "Reuse the existing validation framework" per the task brief: this
module reads validation_summary.csv rather than re-deriving comparison logic from scratch.

For metrics with no validation_summary.csv row (several DISCLOSE/NOT_DETERMINABLE metrics
honestly flagged as unvalidated in metric_reconstruction.md), returns UNVERIFIED, never a
fabricated MATCH.
"""
import csv
import os
from dataclasses import dataclass

# The package root, derived from this file's location rather than from the absolute path of
# the machine the export was built on -- that path is correct exactly once, on that machine,
# and a deployed copy of the same package sits somewhere else. `AI_ANALYTICS_BASE` overrides
# it where a deployment mounts the evidence elsewhere. The evidence itself is unchanged.
BASE = os.environ.get("AI_ANALYTICS_BASE") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
VALIDATION_SUMMARY_PATH = os.path.join(BASE, "validation_summary.csv")


@dataclass(frozen=True)
class ValidationRow:
    metric_id: str
    metric_name: str
    reconstructed_value: str
    reference_value: str
    absolute_difference: str
    percentage_difference: str
    validation_status: str
    reference_source: str
    explanation: str


class ValidationIndex:
    """validation_summary.csv rows are keyed by a script-internal id (REV.01, AR.04a, etc.),
    not by semantic metric_id -- this index maps metric_id -> the rows whose id PREFIX matches
    the metric's own family code, since that's the only stable join key that survived from
    Phase E (the two registries were built in different passes and were never given a shared
    key column -- documented here rather than silently assumed)."""

    _PREFIX_MAP = {
        "M.REV.001": ("REV.01",), "M.REV.002": ("REV.02", "REV.03"),
        "M.EXP.001": ("EXP.01", "EXP.05"), "M.EXP.002": ("EXP.02", "EXP.03", "EXP.04", "EXP.06"),
        "M.PROFIT.001": ("PROFIT.01", "PROFIT.02", "PROFIT.05", "PROFIT.06"),
        "M.OWN.001": ("OWNPAY.01", "OWNPAY.02", "OWNPAY.03"),
        "M.OWN.002": ("PROFIT.03", "PROFIT.04"),
        "M.AR.001A": ("AR.01",), "M.AR.001B": ("AR.02", "AR.03"),
        "M.AR.001D": ("AR.04a", "AR.04b"), "M.AR.002": ("AR.04c",), "M.RISK.001": ("AR.04c",),
        "M.DEP.001": ("DEP.01", "DEP.02"), "M.DEP.002": ("DEP.03", "DEP.04", "DEP.05"),
        "M.RISK.004": ("DEP.06", "DEP.07"),
        "M.OCC.001": ("OCC.01", "OCC.02", "OCC.03", "OCC.04", "OCC.05", "OCC.06", "OCC.07",
                      "OCC.07b", "OCC.08", "OCC.08b", "OCC.09"),
        "M.TEN.001": ("OCC.13",), "M.TEN.002": ("OCC.14",), "M.TEN.003": ("OCC.11",),
        "M.MAINT.001": ("MAINT.01", "MAINT.01b", "MAINT.06"),
        "M.MAINT.002": ("MAINT.02", "MAINT.03", "MAINT.04", "MAINT.05"),
        "M.EB.002": ("EB.01", "EB.02"), "M.EB.001": ("EB.03", "EB.04", "EB.05", "EB.06", "EB.07", "EB.08"),
        "M.COL.001": ("COLL.01",), "M.COL.003": ("COLL.02", "COLL.03"),
        "M.INV.001": ("DQ.001", "DQ.001pct"), "M.RISK.005": ("DQ.013", "DQ.013b"),
        "M.RISK.007": ("DQ.003",),
        "M.TB.001": ("LEDGER.01", "LEDGER.02", "LEDGER.03", "LEDGER.04", "LEDGER.05",
                     "LEDGER.06", "LEDGER.07", "LEDGER.08"),
    }

    def __init__(self, path=VALIDATION_SUMMARY_PATH):
        self._by_check_id = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    self._by_check_id[row["metric_id"]] = ValidationRow(**{
                        k: row[k] for k in ValidationRow.__dataclass_fields__
                    })

    def row(self, check_id):
        """One stored check by its id, or None."""
        return self._by_check_id.get(check_id)

    def rows_for(self, metric_id):
        check_ids = self._PREFIX_MAP.get(metric_id, ())
        return [self._by_check_id[c] for c in check_ids if c in self._by_check_id]

    def status_for(self, metric_id):
        rows = self.rows_for(metric_id)
        if not rows:
            return "UNVERIFIED", "No prior validation_summary.csv check maps to this metric_id."
        statuses = {r.validation_status for r in rows}
        if "DIFFERS" in statuses:
            differing = [r for r in rows if r.validation_status == "DIFFERS"]
            return "DIFFERS", "; ".join(f"{r.metric_id}: {r.explanation}" for r in differing)
        if statuses == {"MATCH"}:
            return "MATCH", f"{len(rows)} prior check(s) all MATCH ({', '.join(r.metric_id for r in rows)})."
        return "PARTIAL", "; ".join(f"{r.metric_id}={r.validation_status}" for r in rows)
