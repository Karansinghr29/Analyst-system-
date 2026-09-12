"""
source_lineage.py -- Source / Evidence / Lineage foundation (production slice 1).

Architectural contract
----------------------
Actual DB source objects (table / view / function)
        ↓
Exported CSV evidence (reproducible snapshot)
        ↓
Source lineage / evidence mapping  ← this module
        ↓
Validation → Semantic definitions → Metric engine → …

CSV filenames are NOT business definitions. This module distinguishes:

    Evidence file          -- opaque export filename from file_manifest.csv
    Actual source object   -- schema-qualified name when the package identifies one
    Source type            -- base_table | view | functions | diagnostic | metadata
    Source lineage confidence
    Calculation / date / filter fields already documented on the semantic registry
    Validation status      -- from validation_reference / validation_summary when present

Rules
-----
* Never invent table / view / function names.
* If the exported package cannot establish the actual source object, record exactly:
  "Not determinable from exported evidence."
* Do not replace CSV evidence; lineage sits on top of the manifest + semantic registries.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from engine.result import NOT_DETERMINABLE_TEXT

# ---------------------------------------------------------------------------
# Confidence vocabulary (evidence-backed only)
# ---------------------------------------------------------------------------
CONF_HIGH = "HIGH"          # manifest logical_name is schema-qualified (public.*)
CONF_MEDIUM = "MEDIUM"      # resolved to a manifest key; logical_name may be nickname
CONF_LOW = "LOW"            # named in semantic prose only; no manifest resolution
CONF_ND = "NOT_DETERMINABLE"


@dataclass(frozen=True)
class SourceObjectRef:
    """One concrete or undeterminable source object behind a semantic artifact."""
    declared_name: str              # as written in registry / prose
    source_type: str                # manifest class or "unknown"
    actual_source_object: str       # public.x when known, else NOT_DETERMINABLE_TEXT
    manifest_key: str               # F.001 / T.receipts / H.003 / UNRESOLVED
    evidence_file: str              # exported CSV filename (may be empty if unresolved)
    row_count: str = ""
    lineage_confidence: str = CONF_ND
    note: str = ""

    @property
    def source_established(self) -> bool:
        return (
            bool(self.actual_source_object)
            and self.actual_source_object != NOT_DETERMINABLE_TEXT
            and self.manifest_key not in ("", "UNRESOLVED")
        )


@dataclass(frozen=True)
class LineageRecord:
    """Lineage for one semantic artifact (metric, DQ finding, diagnostic, conflict)."""
    artifact_kind: str              # metric | dq | diagnostic | conflict | manifest
    artifact_id: str
    display_name: str = ""
    source_objects: tuple = ()      # SourceObjectRef
    source_columns: str = ""
    date_basis: str = ""
    historical_policy: str = ""
    calculation_logic: str = ""     # definition / reconstruction prose from registry
    filters: str = ""
    reversal_treatment: str = ""
    deletion_treatment: str = ""
    grain: str = ""
    validation_reference: str = ""
    validation_status: str = ""     # from validation_summary when matchable
    conflict_ids: tuple = ()
    dq_ids: tuple = ()
    trust_level: str = ""
    export_as_of: str = ""          # from historical_policy when ISO dates present
    overall_confidence: str = CONF_ND
    limitations: tuple = ()
    evidence_only: bool = False     # True when only CSV evidence, no DB object name

    def summary_lines(self) -> tuple:
        """Owner/analyst facing lines — no invented objects."""
        lines = [
            f"{self.artifact_kind.upper()} {self.artifact_id}"
            + (f" — {self.display_name}" if self.display_name else ""),
        ]
        if not self.source_objects:
            lines.append(f"Actual source object: {NOT_DETERMINABLE_TEXT}")
        for ref in self.source_objects:
            lines.append(
                f"Source: declared={ref.declared_name!r}; "
                f"type={ref.source_type}; "
                f"actual={ref.actual_source_object}; "
                f"manifest={ref.manifest_key}; "
                f"evidence_file={ref.evidence_file or NOT_DETERMINABLE_TEXT}; "
                f"confidence={ref.lineage_confidence}"
            )
        if self.date_basis:
            lines.append(f"Date basis: {self.date_basis}")
        if self.historical_policy:
            lines.append(f"Historical policy: {self.historical_policy[:180]}")
        if self.validation_reference:
            lines.append(f"Validation reference: {self.validation_reference[:160]}")
        if self.validation_status:
            # A stored offline result looked up by reference name -- not a comparison of the
            # live value, so it is labelled as a record rather than as this figure's status.
            lines.append(f"Offline validation record: {self.validation_status} "
                         f"(stored result, not a live comparison)")
        if self.trust_level:
            lines.append(f"Trust level: {self.trust_level}")
        if self.conflict_ids:
            lines.append(f"Conflicts: {', '.join(self.conflict_ids)}")
        if self.dq_ids:
            lines.append(f"DQ findings: {', '.join(self.dq_ids)}")
        for lim in self.limitations:
            lines.append(f"Limitation: {lim}")
        lines.append(f"Overall lineage confidence: {self.overall_confidence}")
        return tuple(lines)


# ---------------------------------------------------------------------------
# Manifest / registry accessors
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _manifest_index():
    from engine.evidence_loader import manifest
    df = manifest()
    by_key, by_bare, by_logical = {}, {}, {}
    for _, r in df.iterrows():
        rec = {
            "key": str(r.get("key", "")),
            "logical_name": str(r.get("logical_name", "")),
            "class": str(r.get("class", "")),
            "rows": str(r.get("rows", "")),
            "file": str(r.get("file", "")),
            "note": str(r.get("note", "")),
        }
        by_key[rec["key"]] = rec
        logical = rec["logical_name"].strip()
        if logical:
            by_logical[logical.lower()] = rec
        bare = logical.split(".")[-1].strip().lower()
        if bare:
            by_bare.setdefault(bare, rec)
        if rec["key"].startswith("FN.") and "." in rec["key"]:
            by_bare.setdefault(rec["key"].split(".", 1)[1].strip().lower(), rec)
        if bare.startswith("fn__"):
            by_bare.setdefault(bare[4:], rec)
        if rec["key"].startswith("H.") and bare and not bare.startswith("v_"):
            by_bare.setdefault(f"v_{bare}", rec)
    return by_key, by_bare, by_logical


@lru_cache(maxsize=1)
def _validation_by_reference():
    """Map loose reference tokens → validation_status from validation_summary.csv."""
    import os
    import pandas as pd
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "validation_summary.csv",
    )
    if not os.path.isfile(path):
        return {}
    try:
        df = pd.read_csv(path)
    except Exception:
        return {}
    out = {}
    for _, r in df.iterrows():
        status = str(r.get("validation_status", r.get("status", "")) or "")
        ref = str(r.get("reference_source", r.get("check_id", "")) or "")
        check = str(r.get("check_id", "") or "")
        for tok in (ref, check):
            if tok and tok not in out:
                out[tok] = status
            for m in re.finditer(r"\b([FTH]\.[A-Za-z0-9_]+)\b", tok):
                out.setdefault(m.group(1), status)
    return out


def _confidence_for_manifest_rec(rec) -> str:
    logical = (rec.get("logical_name") or "").strip()
    if logical.lower().startswith("public."):
        return CONF_HIGH
    if rec.get("key"):
        return CONF_MEDIUM
    return CONF_ND


def _actual_object_from_rec(rec) -> str:
    logical = (rec.get("logical_name") or "").strip()
    if not logical:
        return NOT_DETERMINABLE_TEXT
    if logical.lower().startswith("public."):
        return logical
    # Nickname-only diagnostic / metadata — package did not export schema-qualified name
    return NOT_DETERMINABLE_TEXT


def resolve_manifest_key(key: str) -> Optional[SourceObjectRef]:
    """Resolve a single F.*/T.*/H.*/M.*/FN.* key from the evidence package."""
    if not key:
        return None
    by_key, _, _ = _manifest_index()
    rec = by_key.get(key)
    if rec is None:
        return SourceObjectRef(
            declared_name=key,
            source_type="unknown",
            actual_source_object=NOT_DETERMINABLE_TEXT,
            manifest_key="UNRESOLVED",
            evidence_file="",
            lineage_confidence=CONF_ND,
            note=f"Manifest key {key!r} is absent from file_manifest.csv.",
        )
    actual = _actual_object_from_rec(rec)
    conf = _confidence_for_manifest_rec(rec)
    return SourceObjectRef(
        declared_name=rec["logical_name"] or key,
        source_type=rec.get("class") or "unknown",
        actual_source_object=actual,
        manifest_key=rec["key"],
        evidence_file=rec.get("file") or "",
        row_count=rec.get("rows") or "",
        lineage_confidence=conf,
        note=rec.get("note") or "",
    )


def resolve_declared_name(name: str) -> SourceObjectRef:
    """Resolve a declared table/view/function token against the manifest only."""
    from engine import citation as citation_mod
    citations, _ = citation_mod.cite_objects(name)
    if not citations:
        return SourceObjectRef(
            declared_name=name,
            source_type="unknown",
            actual_source_object=NOT_DETERMINABLE_TEXT,
            manifest_key="UNRESOLVED",
            evidence_file="",
            lineage_confidence=CONF_ND,
            note="No object-shaped token resolved against file_manifest.csv.",
        )
    cit = citations[0]
    if not cit.resolved:
        return SourceObjectRef(
            declared_name=name,
            source_type="unknown",
            actual_source_object=NOT_DETERMINABLE_TEXT,
            manifest_key="UNRESOLVED",
            evidence_file="",
            lineage_confidence=CONF_ND,
            note=cit.note or NOT_DETERMINABLE_TEXT,
        )
    by_key, _, _ = _manifest_index()
    rec = by_key.get(cit.manifest_key, {})
    actual = _actual_object_from_rec(rec) if rec else NOT_DETERMINABLE_TEXT
    return SourceObjectRef(
        declared_name=cit.object_name,
        source_type=cit.object_class or (rec.get("class") if rec else "unknown") or "unknown",
        actual_source_object=actual,
        manifest_key=cit.manifest_key,
        evidence_file=cit.file or "",
        row_count=cit.rows or "",
        lineage_confidence=_confidence_for_manifest_rec(rec) if rec else CONF_LOW,
        note="",
    )


def _split_ids(text) -> tuple:
    if not text:
        return ()
    parts = re.split(r"[;,|]\s*", str(text).strip())
    return tuple(p for p in parts if p)


def _overall_confidence(refs: tuple) -> str:
    if not refs:
        return CONF_ND
    order = {CONF_HIGH: 3, CONF_MEDIUM: 2, CONF_LOW: 1, CONF_ND: 0}
    return min(refs, key=lambda r: order.get(r.lineage_confidence, 0)).lineage_confidence


def _lookup_validation_status(validation_reference: str) -> str:
    if not validation_reference:
        return ""
    index = _validation_by_reference()
    if validation_reference in index:
        return index[validation_reference]
    for m in re.finditer(r"\b([FTH]\.[A-Za-z0-9_]+|REV\.\d+|COL\.\d+|EXP\.\d+)\b",
                         validation_reference):
        if m.group(1) in index:
            return index[m.group(1)]
    for key, status in index.items():
        if key and key in validation_reference:
            return status
    return ""


def _export_as_of_from_policy(policy: str) -> str:
    """Extract ISO date range endpoints when present; else empty (not invented)."""
    if not policy:
        return ""
    dates = re.findall(r"20\d{2}-\d{2}-\d{2}", policy)
    if len(dates) >= 2:
        return f"{dates[0]} to {dates[-1]}"
    if len(dates) == 1:
        return dates[0]
    return ""


# ---------------------------------------------------------------------------
# Public resolvers
# ---------------------------------------------------------------------------

def lineage_for_manifest(key: str) -> LineageRecord:
    ref = resolve_manifest_key(key)
    refs = (ref,) if ref else ()
    limitations = []
    if ref and ref.actual_source_object == NOT_DETERMINABLE_TEXT:
        limitations.append(
            "Exported evidence maps this key to a CSV snapshot, but the package does not "
            "establish a schema-qualified DB object name for it."
        )
    return LineageRecord(
        artifact_kind="manifest",
        artifact_id=key,
        display_name=(ref.declared_name if ref else ""),
        source_objects=refs,
        overall_confidence=_overall_confidence(refs),
        limitations=tuple(limitations),
        evidence_only=bool(ref and ref.actual_source_object == NOT_DETERMINABLE_TEXT
                           and ref.evidence_file),
    )


def lineage_for_metric(metric_id: str, registry=None) -> LineageRecord:
    """Build lineage for a semantic metric from registry + manifest (no invention)."""
    from engine.semantic_registry import SemanticRegistry
    reg = registry or SemanticRegistry()
    if metric_id not in reg:
        return LineageRecord(
            artifact_kind="metric",
            artifact_id=metric_id,
            overall_confidence=CONF_ND,
            limitations=(f"Metric {metric_id!r} is not in semantic_metric_registry.csv. "
                         f"{NOT_DETERMINABLE_TEXT}",),
        )
    spec = reg.get(metric_id)
    from engine import citation as citation_mod
    citations, _prose = citation_mod.cite_objects(spec.source_objects or "")
    refs = []
    by_key, _, _ = _manifest_index()
    for cit in citations:
        if cit.resolved:
            rec = by_key.get(cit.manifest_key, {})
            actual = _actual_object_from_rec(rec) if rec else NOT_DETERMINABLE_TEXT
            refs.append(SourceObjectRef(
                declared_name=cit.object_name,
                source_type=cit.object_class or "unknown",
                actual_source_object=actual,
                manifest_key=cit.manifest_key,
                evidence_file=cit.file or "",
                row_count=cit.rows or "",
                lineage_confidence=_confidence_for_manifest_rec(rec) if rec else CONF_LOW,
            ))
        else:
            refs.append(SourceObjectRef(
                declared_name=cit.object_name,
                source_type="unknown",
                actual_source_object=NOT_DETERMINABLE_TEXT,
                manifest_key="UNRESOLVED",
                evidence_file="",
                lineage_confidence=CONF_ND,
                note=cit.note or NOT_DETERMINABLE_TEXT,
            ))
    refs = tuple(refs)
    limitations = []
    unresolved = [r for r in refs if not r.source_established]
    if unresolved:
        limitations.append(
            f"{len(unresolved)} declared source token(s) have no schema-qualified object "
            f"in the exported package ({', '.join(r.declared_name for r in unresolved[:5])})."
        )
    if not refs:
        limitations.append(
            f"No source objects could be resolved for {metric_id}. {NOT_DETERMINABLE_TEXT}"
        )

    vref = getattr(spec, "validation_reference", "") or ""
    return LineageRecord(
        artifact_kind="metric",
        artifact_id=metric_id,
        display_name=getattr(spec, "semantic_name", "") or "",
        source_objects=refs,
        source_columns=getattr(spec, "source_columns", "") or "",
        date_basis=getattr(spec, "date_field", "") or "",
        historical_policy=getattr(spec, "historical_policy", "") or "",
        calculation_logic=(getattr(spec, "definition", "") or "")[:500],
        filters=getattr(spec, "filters", "") or "",
        reversal_treatment=getattr(spec, "reversal_policy", "") or "",
        deletion_treatment=getattr(spec, "soft_delete_policy", "") or "",
        grain=getattr(spec, "grain", "") or "",
        validation_reference=vref,
        validation_status=_lookup_validation_status(vref),
        conflict_ids=_split_ids(getattr(spec, "conflict_ids", "") or ""),
        dq_ids=_split_ids(getattr(spec, "dq_ids", "") or ""),
        trust_level=getattr(spec, "trust_level", "") or "",
        export_as_of=_export_as_of_from_policy(getattr(spec, "historical_policy", "") or ""),
        overall_confidence=_overall_confidence(refs),
        limitations=tuple(limitations),
        evidence_only=bool(refs) and all(
            r.actual_source_object == NOT_DETERMINABLE_TEXT for r in refs),
    )


def lineage_for_dq(dq_id: str) -> LineageRecord:
    """DQ findings cite evidence_files (usually H.* keys) — resolve those only."""
    import os
    import pandas as pd
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data_quality_registry.csv",
    )
    if not os.path.isfile(path):
        return LineageRecord(
            artifact_kind="dq",
            artifact_id=dq_id,
            overall_confidence=CONF_ND,
            limitations=(f"data_quality_registry.csv missing. {NOT_DETERMINABLE_TEXT}",),
        )
    df = pd.read_csv(path)
    id_col = "dq_id" if "dq_id" in df.columns else df.columns[0]
    rows = df[df[id_col].astype(str) == dq_id]
    if rows.empty:
        return LineageRecord(
            artifact_kind="dq",
            artifact_id=dq_id,
            overall_confidence=CONF_ND,
            limitations=(f"DQ id {dq_id!r} not found. {NOT_DETERMINABLE_TEXT}",),
        )
    row = rows.iloc[0]
    evidence = str(row.get("evidence_files", "") or "")
    keys = re.findall(r"\b(H\.[A-Za-z0-9_]+)\b", evidence)
    refs = []
    for key in keys:
        ref = resolve_manifest_key(key)
        if ref:
            refs.append(ref)
    if not refs and evidence.strip():
        refs.append(SourceObjectRef(
            declared_name=evidence.strip()[:120],
            source_type="unknown",
            actual_source_object=NOT_DETERMINABLE_TEXT,
            manifest_key="UNRESOLVED",
            evidence_file="",
            lineage_confidence=CONF_ND,
            note="evidence_files prose did not contain a resolvable H.* key.",
        ))
    refs = tuple(refs)
    title = str(row.get("title", row.get("finding", "")) or "")
    return LineageRecord(
        artifact_kind="dq",
        artifact_id=dq_id,
        display_name=title,
        source_objects=refs,
        calculation_logic=str(row.get("root_cause", "") or "")[:400],
        overall_confidence=_overall_confidence(refs),
        limitations=() if refs and any(r.evidence_file for r in refs) else (
            f"No exported evidence file established for {dq_id}. {NOT_DETERMINABLE_TEXT}",
        ),
        evidence_only=bool(refs) and all(
            r.actual_source_object == NOT_DETERMINABLE_TEXT for r in refs),
    )


def lineage_for_diagnostic(h_key: str) -> LineageRecord:
    return lineage_for_manifest(h_key)


def coverage_report(registry=None) -> dict:
    """Summarise lineage coverage across the semantic metric registry (no mutations)."""
    from engine.semantic_registry import SemanticRegistry
    reg = registry or SemanticRegistry()
    totals = {
        "metrics_total": 0,
        "metrics_with_any_resolved_manifest": 0,
        "metrics_with_schema_qualified_object": 0,
        "metrics_evidence_file_only": 0,
        "metrics_fully_undeterminable": 0,
        "by_confidence": {CONF_HIGH: 0, CONF_MEDIUM: 0, CONF_LOW: 0, CONF_ND: 0},
    }
    for mid in reg.all_ids():
        totals["metrics_total"] += 1
        rec = lineage_for_metric(mid, registry=reg)
        totals["by_confidence"][rec.overall_confidence] = (
            totals["by_confidence"].get(rec.overall_confidence, 0) + 1
        )
        if any(r.manifest_key not in ("", "UNRESOLVED") for r in rec.source_objects):
            totals["metrics_with_any_resolved_manifest"] += 1
        if any(r.actual_source_object != NOT_DETERMINABLE_TEXT for r in rec.source_objects):
            totals["metrics_with_schema_qualified_object"] += 1
        elif rec.source_objects and any(r.evidence_file for r in rec.source_objects):
            totals["metrics_evidence_file_only"] += 1
        if not rec.source_objects or all(
                r.manifest_key in ("", "UNRESOLVED") for r in rec.source_objects):
            totals["metrics_fully_undeterminable"] += 1
    return totals


# Part I classification vocabulary for this foundation + known gaps
CAPABILITY_STATUS = {
    "source_lineage_resolution": "IMPLEMENTED_WITH_LIMITATIONS",
    "forecasting": "NOT_IMPLEMENTED",
    "scenario_analysis": "NOT_IMPLEMENTED",
    "anomaly_detection": "IMPLEMENTED_WITH_LIMITATIONS",
    "statistical_summary": "NOT_IMPLEMENTED",
    "kpi_lookup": "IMPLEMENTED_AND_VALIDATED",
    "period_comparison": "IMPLEMENTED_AND_VALIDATED",
    "driver_analysis": "IMPLEMENTED_WITH_LIMITATIONS",
}
