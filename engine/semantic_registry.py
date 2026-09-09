"""
semantic_registry.py -- loads semantic_metric_registry.csv (the Phase-C-onward source of truth
for every metric's trust level, grain, filters, and evidence references) and cross-checks it
against metric_registry.csv (required: 0 drift, per Phase C's own verification pass).

This module NEVER computes a business value -- it only resolves metric_id -> MetricSpec.
"""
import csv
import os
from dataclasses import dataclass, field

# The package root, derived from this file's location rather than from the absolute path of
# the machine the export was built on -- that path is correct exactly once, on that machine,
# and a deployed copy of the same package sits somewhere else. `AI_ANALYTICS_BASE` overrides
# it where a deployment mounts the evidence elsewhere. The evidence itself is unchanged.
BASE = os.environ.get("AI_ANALYTICS_BASE") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
SEMANTIC_REGISTRY_PATH = os.path.join(BASE, "semantic_metric_registry.csv")
LEGACY_REGISTRY_PATH = os.path.join(BASE, "metric_registry.csv")

VALID_TRUST_LEVELS = {"SAFE", "DISCLOSE", "SHOW_BOTH", "BLOCK", "NOT_DETERMINABLE"}


@dataclass(frozen=True)
class MetricSpec:
    metric_id: str
    semantic_name: str
    display_name: str
    domain: str
    description: str
    definition: str
    source_objects: str
    source_columns: str
    grain: str
    dimensions: str
    date_field: str
    aggregation: str
    filters: str
    reversal_policy: str
    soft_delete_policy: str
    historical_policy: str
    dependency_metrics: tuple = field(default_factory=tuple)
    validation_reference: str = ""
    conflict_ids: tuple = field(default_factory=tuple)
    dq_ids: tuple = field(default_factory=tuple)
    trust_level: str = "NOT_DETERMINABLE"
    ai_handling: str = "NOT_DETERMINABLE"
    caveat_text: str = ""
    status: str = ""

    @property
    def is_family(self):
        """True for metrics whose `definition` documents more than one competing sub-definition
        (Def A/B/C/D, or Def i/ii/iii) within a single metric_id -- these must never be
        collapsed to one number even though they carry one metric_id (semantic_layer.md)."""
        d = self.definition
        return ("Def A" in d) or ("Def i " in d) or ("Def i(" in d) or ("Def A " in d) or \
               ("Def A:" in d) or ("Def 1" in d) or ("Definition A" in d)


def _split(s):
    return tuple(x.strip() for x in s.split(";") if x.strip()) if s else tuple()


class SemanticRegistry:
    def __init__(self, path=SEMANTIC_REGISTRY_PATH):
        self._by_id = {}
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                trust = row["trust_level"].strip()
                if trust not in VALID_TRUST_LEVELS:
                    raise ValueError(f"{row['metric_id']}: unknown trust_level {trust!r}")
                spec = MetricSpec(
                    metric_id=row["metric_id"],
                    semantic_name=row["semantic_name"],
                    display_name=row["display_name"],
                    domain=row["domain"],
                    description=row["description"],
                    definition=row["definition"],
                    source_objects=row["source_objects"],
                    source_columns=row["source_columns"],
                    grain=row["grain"],
                    dimensions=row["dimensions"],
                    date_field=row["date_field"],
                    aggregation=row["aggregation"],
                    filters=row["filters"],
                    reversal_policy=row["reversal_policy"],
                    soft_delete_policy=row["soft_delete_policy"],
                    historical_policy=row["historical_policy"],
                    dependency_metrics=_split(row["dependency_metrics"]),
                    validation_reference=row["validation_reference"],
                    conflict_ids=_split(row["conflict_ids"]),
                    dq_ids=_split(row["dq_ids"]),
                    trust_level=trust,
                    ai_handling=row["ai_handling"],
                    caveat_text=row["caveat_text"],
                    status=row["status"],
                )
                self._by_id[spec.metric_id] = spec

    def get(self, metric_id):
        if metric_id not in self._by_id:
            raise KeyError(
                f"{metric_id!r} is not a semantic metric. Not determinable from exported "
                f"evidence -- no such metric_id exists in semantic_metric_registry.csv."
            )
        return self._by_id[metric_id]

    def __contains__(self, metric_id):
        return metric_id in self._by_id

    def all_ids(self):
        return list(self._by_id.keys())

    def family_members(self, metric_id):
        """For AR.001A-D style families that ARE separate metric_ids (not sub-definitions
        within one row), return every sibling id sharing the same numeric prefix
        (e.g. M.AR.001A -> [M.AR.001A, M.AR.001B, M.AR.001C, M.AR.001D])."""
        import re
        m = re.match(r"^(M\.[A-Z]+\.\d+)[A-Za-z]?$", metric_id)
        if not m:
            return [metric_id]
        prefix = m.group(1)
        return sorted(k for k in self._by_id if re.match(rf"^{re.escape(prefix)}[A-Za-z]?$", k))


def cross_check_against_legacy_registry(registry: SemanticRegistry):
    """Verification requirement carried forward from the semantic-layer phase: 0 drift between
    semantic_metric_registry.csv and metric_registry.csv on metric_id set, definition text,
    conflict_ids, dq_ids, and historical coverage. Returns a list of mismatch descriptions
    (empty list = clean)."""
    mismatches = []
    legacy = {}
    with open(LEGACY_REGISTRY_PATH, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            legacy[row["metric_id"]] = row

    if set(legacy) != set(registry.all_ids()):
        mismatches.append(f"metric_id set differs: legacy-only={set(legacy)-set(registry.all_ids())}, "
                           f"semantic-only={set(registry.all_ids())-set(legacy)}")

    for mid, spec in registry._by_id.items():
        row = legacy.get(mid)
        if row is None:
            continue
        if row["definition"] != spec.definition:
            mismatches.append(f"{mid}: definition text drift")
        if row["conflict_ids"] != ";".join(spec.conflict_ids):
            mismatches.append(f"{mid}: conflict_ids drift")
        if row["dq_ids"] != ";".join(spec.dq_ids):
            mismatches.append(f"{mid}: dq_ids drift")
        if row["historical_coverage"] != spec.historical_policy:
            mismatches.append(f"{mid}: historical_coverage drift")
        if row["ai_trust_status"] != spec.trust_level:
            mismatches.append(f"{mid}: trust_level drift ({row['ai_trust_status']} vs {spec.trust_level})")
    return mismatches
