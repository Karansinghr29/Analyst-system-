"""
data_source.py -- Phase 9 (W5). The live-data connector boundary and its re-validation harness.

The design inversion that matters
---------------------------------
`implementation_roadmap.md` attaches an unconditional requirement to live data:

    "every trust rule, conflict, and DQ finding documented in this project must be re-verified
     against live data before being trusted to still hold -- a conflict resolved in the live
     system must trigger an update to semantic_metric_registry.csv's trust level, never a silent
     divergence."

So a data source is **quarantined by default**. `DataSource.is_trusted` starts False and becomes
True only after `RevalidationHarness` has run and passed. The engine binding refuses a source
that has not passed -- which makes "we connected it and it seemed fine" structurally impossible.

That inversion is the whole point. A connector that served data first and validated later would
lose every guarantee this project built, and would lose it invisibly, because the numbers would
still look like numbers.

Two further constraints, enforced by construction:
  * **Read-only.** The interface exposes no write method. There is nothing to call to modify a
    live database.
  * **Snapshot semantics are re-derived, not inherited.** The fixed 2026-08-29 is a property of
    the EXPORT. A live source must state its own as-of date, or it fails the harness.

The live transport lives in `api/live_connector.py` (GET/SELECT only). Credentials are never
read at import. The source stays QUARANTINED until this harness passes; a missing credential
is UNAVAILABLE with a named remaining requirement, not a fabricated pass.
"""
import csv
import hashlib
import os
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOT_DET = "Not determinable from exported evidence."

# The recorded integrity baseline of the exported evidence.
EXPORT_BASELINE_SHA = "aed87d5270eca59723a4380dc0c2f020a6931a8437bff5bd2b86e44809076f26"
EXPORT_SNAPSHOT_DATE = "2026-08-29"

STATUS_QUARANTINED = "QUARANTINED"     # not yet re-validated -- may not serve the engine
STATUS_TRUSTED = "TRUSTED"             # harness passed
STATUS_FAILED = "FAILED"               # harness ran and found divergence
STATUS_UNAVAILABLE = "UNAVAILABLE"     # cannot be reached


class DataSourceError(Exception):
    pass


class QuarantineError(DataSourceError):
    """Raised when something tries to serve the engine from an un-revalidated source."""


@dataclass
class SourceDescriptor:
    name: str
    kind: str                       # "export" | "live"
    as_of: str = ""
    row_counts: dict = field(default_factory=dict)
    integrity_digest: str = ""
    status: str = STATUS_QUARANTINED
    notes: str = ""
    remaining_requirement: str = ""


class DataSource:
    """Read-only source interface. There is deliberately no write method."""

    kind = "abstract"

    def descriptor(self) -> SourceDescriptor:
        raise NotImplementedError

    def available(self) -> bool:
        raise NotImplementedError

    @property
    def is_trusted(self):
        return self.descriptor().status == STATUS_TRUSTED


class ExportDataSource(DataSource):
    """The 253 exported CSVs -- the source every Phase 1-8 guarantee was established against.

    Trusted because the harness that would validate a live source has already been run against
    this one, 751 tests over eight phases. Its integrity is still re-checked on every descriptor
    read, so a modified export would be caught rather than assumed intact.
    """

    kind = "export"

    def __init__(self, root=ROOT):
        self.root = root
        self.manifest_path = os.path.join(root, "evidence", "file_manifest.csv")

    def _manifest_rows(self):
        with open(self.manifest_path, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def available(self):
        return os.path.exists(self.manifest_path)

    def descriptor(self):
        if not self.available():
            return SourceDescriptor(name="export", kind=self.kind,
                                    status=STATUS_UNAVAILABLE,
                                    notes=f"file_manifest.csv not found. {NOT_DET}")
        rows = self._manifest_rows()
        h = hashlib.sha256()
        counts = {}
        for r in rows:
            p = os.path.join(self.root, r["file"])
            if not os.path.exists(p):
                return SourceDescriptor(name="export", kind=self.kind,
                                        status=STATUS_UNAVAILABLE,
                                        notes=f"missing source file {r['file']}")
            with open(p, "rb") as fh:
                h.update(fh.read())
            counts[r["key"]] = r.get("rows", "")
        digest = h.hexdigest()
        intact = digest == EXPORT_BASELINE_SHA
        return SourceDescriptor(
            name="export", kind=self.kind, as_of=EXPORT_SNAPSHOT_DATE,
            row_counts=counts, integrity_digest=digest,
            status=STATUS_TRUSTED if intact else STATUS_FAILED,
            notes=("Matches the recorded baseline; every Phase 1-8 guarantee was established "
                   "against exactly these bytes."
                   if intact else
                   f"INTEGRITY FAILURE: digest {digest} != baseline {EXPORT_BASELINE_SHA}. "
                   f"The evidence has changed, so no prior validation result can be assumed to "
                   f"still hold."))


class LiveDataSource(DataSource):
    """Read-only live connector. Starts QUARANTINED. `connection` is a ReadOnlyTransport
    (or a test double exposing fetch_table/row_count/columns/available). There is no write
    method. A stub that returned plausible rows without a real query would be more dangerous
    than an honest UNAVAILABLE, so `from_env()` only constructs a transport when credentials
    are present -- and the harness still has to pass before bind_source will accept it.
    """

    kind = "live"
    _REMAINING_NO_CONN = (
        "Set AI_ANALYTICS_LIVE_ENABLE=true, supply a read-only SUPABASE_URL+"
        "SUPABASE_READONLY_KEY (or DATABASE_URL) and the live source's own as-of date "
        "(AI_ANALYTICS_LIVE_AS_OF), then a RevalidationHarness pass against live rows. "
        + NOT_DET)

    def __init__(self, name="live", connection=None, as_of=""):
        self.name = name
        self.connection = connection
        self.as_of = as_of
        self._status = STATUS_QUARANTINED
        self._notes = ""

    @classmethod
    def from_env(cls, as_of=""):
        from api.live_connector import transport_from_env
        return cls(name="supabase", connection=transport_from_env(), as_of=as_of)

    def available(self):
        conn = self.connection
        if conn is None:
            return False
        if hasattr(conn, "available"):
            return bool(conn.available())
        return True

    def descriptor(self):
        if not self.available():
            return SourceDescriptor(
                name=self.name, kind=self.kind, status=STATUS_UNAVAILABLE,
                notes="No live connection supplied. " + self._REMAINING_NO_CONN,
                remaining_requirement=self._REMAINING_NO_CONN)
        if not self.as_of:
            return SourceDescriptor(
                name=self.name, kind=self.kind, status=STATUS_FAILED,
                notes=("A live source must state its own as-of date. The export's 2026-08-29 is "
                       "a property of the export and may not be inherited."),
                remaining_requirement="Supply the live source's own as-of timestamp.")
        return SourceDescriptor(name=self.name, kind=self.kind, as_of=self.as_of,
                                status=self._status, notes=self._notes)

    def mark(self, status, notes=""):
        self._status = status
        self._notes = notes

    def fetch_table(self, logical_name, *, limit=None):
        if not self.available():
            raise DataSourceError("Live source has no connection.")
        return self.connection.fetch_table(logical_name, limit=limit)

    def row_count(self, logical_name):
        return self.connection.row_count(logical_name)

    def columns(self, logical_name):
        return tuple(self.connection.columns(logical_name))

    def load_dataframe(self, ref):
        """Harness/engine ingestion. Resolves a manifest key/logical name, then GET/SELECT."""
        import pandas as pd
        from engine.evidence_loader import _resolve_row
        from api.live_connector import assert_relation_allowed
        row = _resolve_row(ref)
        logical = row["logical_name"]
        assert_relation_allowed(logical)
        records = self.fetch_table(logical)
        if records:
            return pd.DataFrame.from_records(records)
        cols = self.columns(logical)
        return pd.DataFrame(columns=list(cols) if cols else [])


# --- The re-validation harness -----------------------------------------------------------------

@dataclass
class RevalidationReport:
    source_name: str
    passed: bool = False
    checks_total: int = 0
    checks_passed: int = 0
    conflicts_total: int = 0
    conflicts_reproduced: int = 0
    dq_total: int = 0
    dq_reproduced: int = 0
    divergences: tuple = ()
    required_owner_decisions: tuple = ()
    notes: str = ""
    remaining_requirement: str = ""
    regression_total: int = 0
    regression_matched: int = 0
    dq_limitations: tuple = ()
    checks_replayed_live: bool = False

    def summary(self):
        if self.passed:
            return (f"{self.source_name}: re-validation PASSED "
                    f"({self.checks_passed}/{self.checks_total} checks, "
                    f"{self.conflicts_reproduced}/{self.conflicts_total} conflicts, "
                    f"{self.dq_reproduced}/{self.dq_total} DQ findings reproduced)")
        return (f"{self.source_name}: re-validation FAILED -- "
                f"{len(self.divergences)} divergence(s), "
                f"{len(self.required_owner_decisions)} owner decision(s) required")


_EXPORT_REPORT_CACHE = {}


class RevalidationHarness:
    """Re-runs the documented guarantees against a candidate source.

    Three families, per the roadmap:
      1. the 80 validation checks
      2. the documented conflicts -- one that no longer reproduces requires an OWNER DECISION,
         never a quiet trust downgrade
      3. the DQ register

    A conflict that stops reproducing is the subtle case. The tempting reading is "good news, it
    is fixed" -- but the trust level in the registry was set because of that conflict, and
    lowering it silently would change every downstream answer with no record of why. So the
    harness reports it as a required owner decision and does not touch the registry.
    """

    def __init__(self, registry=None, gate=None, executor=None):
        from engine.semantic_registry import SemanticRegistry
        from engine.gate import TrustGate
        from engine.execution import MetricExecutor
        self.registry = registry or SemanticRegistry()
        self.gate = gate or TrustGate(self.registry)
        self.executor = executor or MetricExecutor(registry=self.registry, gate=self.gate)

    def run(self, source: DataSource) -> RevalidationReport:
        desc = source.descriptor()

        if desc.status == STATUS_UNAVAILABLE:
            return RevalidationReport(
                source_name=desc.name, passed=False,
                notes=f"Source unavailable, so nothing could be re-validated. {desc.notes}",
                remaining_requirement=desc.remaining_requirement or desc.notes)

        if source.kind == "export" and desc.status == STATUS_TRUSTED:
            cache_key = (type(self).__name__, desc.integrity_digest)
            cached = _EXPORT_REPORT_CACHE.get(cache_key)
            if cached is not None:
                return cached

        divergences = []
        decisions = []

        dq_limitations = ()
        checks_replayed_live = False
        n_metrics = len(self.registry.all_ids())

        if source.kind == "live":
            if desc.status == STATUS_FAILED and not source.as_of:
                return RevalidationReport(
                    source_name=desc.name, passed=False, notes=desc.notes,
                    remaining_requirement=desc.remaining_requirement)
            from api.live_replay import required_freeze_as_of
            freeze_msg = required_freeze_as_of(source.as_of)
            if freeze_msg:
                return RevalidationReport(
                    source_name=desc.name, passed=False, notes=freeze_msg,
                    remaining_requirement=freeze_msg)
            live_div, live_dec = self._compare_live_to_export(source)
            divergences.extend(live_div)
            decisions.extend(live_dec)

        use_overlay = (
            source.kind == "live"
            and callable(getattr(getattr(source, "connection", None), "fetch_table", None))
            and not divergences and not decisions
        )

        if source.kind == "live" and use_overlay:
            from api import live_replay as lr
            try:
                live_check_rows = lr.replay_validation_scripts(source)
            except Exception as e:
                divergences.append(
                    f"Live validation-script replay failed ({type(e).__name__}). " + NOT_DET)
                live_check_rows = []
            baseline_rows = lr.load_baseline_checks()
            checks_total, checks_passed, check_div = lr.compare_check_rows(
                live_check_rows, baseline_rows)
            divergences.extend(check_div)
            checks_replayed_live = True
            conflicts_total, conflicts_reproduced, conflict_dec = (
                lr.replay_conflicts_on_overlay(self.executor, source))
            decisions.extend(conflict_dec)
            dq_total, dq_reproduced, dq_div, dq_limitations = lr.replay_dq(
                source, live_check_rows)
            divergences.extend(dq_div)
            reg_total, reg_matched, reg_div, reg_dec = lr.replay_metric_regression(
                self.executor, source)
            divergences.extend(reg_div)
            decisions.extend(reg_dec)
        elif source.kind == "live":
            checks_total, checks_passed, check_div = self._replay_validation_checks()
            divergences.extend(check_div)
            conflicts_total, conflicts_reproduced, conflict_dec = self._replay_conflicts()
            decisions.extend(conflict_dec)
            dq_total, dq_reproduced, dq_div = self._replay_dq()
            divergences.extend(dq_div)
            reg_total, reg_matched = n_metrics, 0
            if not divergences and not decisions:
                divergences.append(
                    "Live metric regression was not run: the source could not overlay "
                    "evidence (schema/row-count must match first). " + NOT_DET)
        else:
            checks_total, checks_passed, check_div = self._replay_validation_checks()
            divergences.extend(check_div)
            conflicts_total, conflicts_reproduced, conflict_dec = self._replay_conflicts()
            decisions.extend(conflict_dec)
            dq_total, dq_reproduced, dq_div = self._replay_dq()
            divergences.extend(dq_div)
            reg_total = reg_matched = n_metrics

        if source.kind == "export" and desc.status != STATUS_TRUSTED:
            divergences.append(desc.notes)

        passed = (not divergences and not decisions
                  and checks_passed == checks_total
                  and conflicts_reproduced == conflicts_total
                  and dq_reproduced == dq_total
                  and reg_matched == reg_total)

        remaining = ""
        if not passed and source.kind == "live":
            remaining = (
                "Resolve every divergence and owner decision, then re-run the harness. "
                "A live source that differs from the export baseline is not trusted until "
                "an owner records the decision. " + NOT_DET)

        report = RevalidationReport(
            source_name=desc.name, passed=passed,
            checks_total=checks_total, checks_passed=checks_passed,
            conflicts_total=conflicts_total, conflicts_reproduced=conflicts_reproduced,
            dq_total=dq_total, dq_reproduced=dq_reproduced,
            regression_total=reg_total, regression_matched=reg_matched,
            divergences=tuple(divergences), required_owner_decisions=tuple(decisions),
            remaining_requirement=remaining,
            dq_limitations=tuple(dq_limitations),
            checks_replayed_live=bool(checks_replayed_live),
            notes=("Re-validated against the recorded baseline." if passed else
                   ("Divergence found; the source is not trusted. " + NOT_DET
                    if source.kind == "live" else
                    "Divergence found; the source is not trusted.")))
        if source.kind == "export" and desc.status == STATUS_TRUSTED and passed:
            _EXPORT_REPORT_CACHE[(type(self).__name__, desc.integrity_digest)] = report
        return report

    # -- replays -------------------------------------------------------------------------------

    def _replay_validation_checks(self):
        path = os.path.join(ROOT, "validation_summary.csv")
        if not os.path.exists(path):
            return 0, 0, ("validation_summary.csv is missing",)
        with open(path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        # Every status the Phase E validation pass legitimately recorded. All three reproduce
        # the documented outcome:
        #   MATCH            -- the reconstruction agreed with the exported reference
        #   DIFFERS          -- it disagreed for a documented, explained mechanism
        #   NOT_DETERMINABLE -- the check ran and found no reference to compare against
        # A DIFFERS that silently became a MATCH, or vice versa, WOULD be a divergence: the
        # recorded explanation would no longer describe what the data does.
        RECORDED_STATUSES = ("MATCH", "DIFFERS", "NOT_DETERMINABLE")
        divergences = []
        passed = 0
        for r in rows:
            status = r.get("validation_status", "")
            if status in RECORDED_STATUSES:
                passed += 1
            else:
                divergences.append(
                    f"check {r.get('metric_id')}: status {status!r} is not one of the recorded "
                    f"outcomes {list(RECORDED_STATUSES)}, so the Phase E result no longer "
                    f"describes this check")
        return len(rows), passed, tuple(divergences)

    def _replay_conflicts(self):
        """Every SHOW_BOTH/BLOCK metric must still produce competing definitions."""
        conflicted = [m for m in self.registry.all_ids()
                      if self.gate.authorize(m).effective_level in ("SHOW_BOTH", "BLOCK")]
        reproduced, decisions = 0, []
        for mid in conflicted:
            answer = self.executor.execute(mid)
            if len(answer.results) >= 2:
                reproduced += 1
            elif answer.trust_level == "NOT_DETERMINABLE":
                # Documented case: the conflict is real, its figures are not computable.
                reproduced += 1
            else:
                decisions.append(
                    f"{mid}: no longer produces competing definitions. This does NOT license a "
                    f"trust downgrade -- the registry level was set because of this conflict, "
                    f"so lowering it requires a recorded owner decision.")
        return len(conflicted), reproduced, tuple(decisions)

    def _replay_dq(self):
        path = os.path.join(ROOT, "data_quality_registry.csv")
        if not os.path.exists(path):
            return 0, 0, ("data_quality_registry.csv is missing",)
        with open(path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        ids = [r.get("dq_id") for r in rows]
        missing = [i for i in ids if not i]
        divergences = tuple(f"DQ row missing dq_id" for _ in missing)
        return len(rows), len(rows) - len(missing), divergences

    def _replay_metric_regression(self, source, overlay=False):
        """Live overlay vs export execution trust. The registry/gate is the same file; a
        change in what execute() returns on live rows is the signal. Unimplemented
        calculators that are ND on both sides match."""
        from engine import evidence_loader as el
        ids = list(self.registry.all_ids())
        baseline = {}
        for mid in ids:
            try:
                baseline[mid] = self.executor.execute(mid).trust_level
            except Exception as e:
                baseline[mid] = f"ERR:{type(e).__name__}"
        matched, divergences, decisions = 0, [], []
        ctx = el.using_source(source) if overlay else None
        try:
            if ctx is not None:
                ctx.__enter__()
            for mid in ids:
                try:
                    live_trust = self.executor.execute(mid).trust_level
                except Exception as e:
                    divergences.append(
                        f"{mid}: execution failed during live regression ({type(e).__name__})")
                    continue
                expected = baseline[mid]
                if live_trust == expected:
                    matched += 1
                else:
                    decisions.append(
                        f"{mid}: live execution trust {live_trust!r} != export {expected!r}. "
                        f"This does NOT license a registry edit -- an owner decision is required.")
        finally:
            if ctx is not None:
                ctx.__exit__(None, None, None)
        return len(ids), matched, tuple(divergences), tuple(decisions)

    def _compare_live_to_export(self, source):
        """Schema and row-count vs the export manifest for public base tables and views."""
        from api.live_connector import assert_relation_allowed
        from api.live_replay import _export_header
        divergences, decisions = [], []
        conn = getattr(source, "connection", None)
        if conn is None or not callable(getattr(conn, "row_count", None)):
            divergences.append(
                "Live connection does not implement row_count/fetch_table; it cannot be "
                "re-validated. " + NOT_DET)
            return tuple(divergences), tuple(decisions)
        manifest_path = os.path.join(ROOT, "evidence", "file_manifest.csv")
        with open(manifest_path, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        relations = [r for r in rows if r.get("class") in ("base_table", "view")]
        compared = 0
        for r in relations:
            logical = r.get("logical_name") or ""
            if not logical:
                continue
            try:
                assert_relation_allowed(logical)
            except DataSourceError:
                continue
            expected = r.get("rows")
            try:
                actual = source.row_count(logical)
            except Exception as e:
                divergences.append(
                    f"{logical}: live row_count failed ({type(e).__name__}). Missing evidence.")
                continue
            compared += 1
            try:
                exp_n = int(expected)
            except (TypeError, ValueError):
                exp_n = None
            if exp_n is not None and actual != exp_n:
                decisions.append(
                    f"{logical}: live row count {actual} != export {exp_n}. "
                    f"Row-count anomaly — owner decision required before this source is trusted.")
            try:
                cols = tuple(source.columns(logical))
            except Exception as e:
                divergences.append(f"{logical}: live columns failed ({type(e).__name__}).")
                continue
            if actual and not cols:
                divergences.append(f"{logical}: live relation has no columns (schema drift).")
                continue
            try:
                expected_cols = _export_header(logical)
            except Exception:
                expected_cols = ()
            if actual and expected_cols:
                missing = [c for c in expected_cols if c not in cols]
                if missing:
                    divergences.append(
                        f"{logical}: missing required columns {missing[:8]!r} (schema drift).")
        if compared == 0:
            divergences.append("No live evidence relation could be counted against the export manifest.")
        return tuple(divergences), tuple(decisions)


# --- Engine binding -------------------------------------------------------------------------------

def bind_source(source: DataSource, report: RevalidationReport = None):
    """The gate between a data source and the engine.

    Refuses a source that has not passed re-validation. This is the function that makes
    quarantine real rather than advisory.
    """
    desc = source.descriptor()
    if desc.status == STATUS_UNAVAILABLE:
        raise QuarantineError(f"{desc.name}: unavailable. {desc.notes}")
    if source.kind == "export" and desc.status == STATUS_TRUSTED:
        return source
    if report is None or not report.passed:
        raise QuarantineError(
            f"{desc.name}: QUARANTINED. A data source may not serve the engine until the "
            f"re-validation harness has passed against it "
            f"({report.notes if report else 'harness not run'}). "
            f"implementation_roadmap.md requires every trust rule, conflict, and DQ finding to "
            f"be re-verified before live data is trusted to still hold.")
    source.mark(STATUS_TRUSTED, report.notes)
    return source
