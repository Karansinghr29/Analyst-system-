"""
common.py -- shared evidence loader for every validate_*.py script.

Single source of truth for:
  - resolving an opaque exported filename to a business object, via evidence/file_manifest.csv
  - loading a table/view/diagnostic as a pandas DataFrame
  - snapshot metadata (export window, row-count timestamp)
  - a shared validation_summary.csv writer so every script appends to ONE file in the
    exact schema the deliverable requires

READ-ONLY. No script in this package writes to any file under the package root except
validation_summary.csv, monthly_validation/*.csv, and files under scripts/validation/.
Never opens a source CSV in 'w' mode.
"""
import os
import sys
import csv
import pandas as pd

# Where the evidence package lives.
#
# This was the absolute path of the machine the export was built on, which is correct exactly
# once -- on that machine. Everywhere else, including a deployed container, the same package
# sits at a different path, so the root is derived from THIS FILE's location: the package root
# is two directories above scripts/validation/. `AI_ANALYTICS_BASE` overrides it for a
# deployment that mounts the evidence somewhere else.
#
# Nothing about the evidence changes. The manifest, the filenames, the row counts and every
# validation result are the same bytes read through a path that is no longer machine-specific.
BASE = os.environ.get("AI_ANALYTICS_BASE") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANIFEST_PATH = os.path.join(BASE, "evidence", "file_manifest.csv")
VALIDATION_SUMMARY = os.path.join(BASE, "validation_summary.csv")
MONTHLY_DIR = os.path.join(BASE, "monthly_validation")

_manifest = None

# Byte-identical duplicate keys -> preferred canonical key. Loading the duplicate key still
# works (it's the same bytes), but resolve-by-logical-name prefers the canonical one.
DUPLICATE_OF = {
    "M.021": "FN.TRG", "H.001b": "H.001", "H.002b": "H.002", "H.010": "F.005",
    "H.015": "F.022", "H.054": "H.017", "H.020b": "H.020", "H.029": "F.028",
    "F.026": "F.025", "H.047": "F.027",
}

# Diagnostics that are known LIMIT-ed samples, not full populations. Loading one prints a
# warning; use the noted full-population key instead when completeness matters.
TRUNCATED = {
    "H.028": "200 of 1213 allotments -- use H.052-equivalent (T164500.151) for the full set",
    "H.036": "LIMIT 500 of 2204 rows -- use F.017 for the full population",
    "H.038": "200 of 33894 journal lines -- row trace only",
    "H.039": "200 of 16451 tenant_transactions -- row trace only",
    "H.040": "200 of 2227 drifting invoices -- use the T163956.045 export for the full population",
    "H.041": "200 of 5858 receipts -- row trace only",
}


def manifest():
    global _manifest
    if _manifest is None:
        _manifest = pd.read_csv(MANIFEST_PATH, encoding="utf-8")
    return _manifest


def _resolve_row(ref):
    m = manifest()
    hit = m[m["key"] == ref]
    if len(hit):
        return hit.iloc[0]
    for cand in (ref, "public." + ref, "market." + ref):
        hit = m[m["logical_name"] == cand]
        if len(hit):
            if len(hit) > 1:
                pref = hit[~hit["key"].isin(DUPLICATE_OF.keys())]
                if len(pref):
                    hit = pref
            return hit.iloc[0]
    raise KeyError(f"{ref!r} is not a manifest key or logical name (see evidence/file_manifest.csv)")


def describe(ref):
    r = _resolve_row(ref)
    print(f"{r['key']:10s} {r['logical_name']:42s} rows={r['rows']:>7} cols={r['cols']:>3} "
          f"file={r['file']}")
    return r


def load(ref, warn=True, **read_csv_kwargs):
    """Load any manifest entry (table / view / diagnostic / metadata) as a DataFrame."""
    row = _resolve_row(ref)
    key = row["key"]
    if warn and key in TRUNCATED:
        print(f"WARNING  {key}: {TRUNCATED[key]}", file=sys.stderr)
    if warn and key in DUPLICATE_OF:
        print(f"NOTE     {key} is byte-identical to {DUPLICATE_OF[key]}", file=sys.stderr)
    path = os.path.join(BASE, row["file"])
    kwargs = dict(encoding="utf-8-sig", low_memory=False)
    kwargs.update(read_csv_kwargs)
    return pd.read_csv(path, **kwargs)


def load_table(name, **kw):
    row = _resolve_row(name)
    if row["class"] != "base_table":
        raise ValueError(f"{name!r} resolves to {row['key']} (class={row['class']}), not a base table")
    return load(row["key"], **kw)


def load_view(name, **kw):
    row = _resolve_row(name)
    if row["class"] != "view":
        raise ValueError(f"{name!r} resolves to {row['key']} (class={row['class']}), not a view")
    return load(row["key"], **kw)


def snapshot():
    s = load("M.002", warn=False).iloc[0]
    e = load("M.099", warn=False).iloc[0]
    rc = load("M.006", warn=False)
    return {
        "start": s["snapshot_at"], "end": e["snapshot_at"],
        "counted_at": rc.iloc[0]["counted_at"], "pg_version": s["pg_version"],
    }


def to_bool(series):
    """Normalise the exported 'true'/'false'/'null' text into real booleans (NaN -> False)."""
    return series.astype(str).str.lower().eq("true")


def money(series):
    """Coerce a numeric-looking column to float, treating blank/'null' as NaN (not 0)."""
    return pd.to_numeric(series, errors="coerce")


# ---------------------------------------------------------------------------
# Shared validation_summary.csv writer
# ---------------------------------------------------------------------------
SUMMARY_COLS = [
    "metric_id", "metric_name", "reconstructed_value", "reference_value",
    "absolute_difference", "percentage_difference", "validation_status",
    "reference_source", "explanation",
]


def _fmt_num(x):
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    try:
        return f"{float(x):.2f}"
    except (TypeError, ValueError):
        return str(x)


def record_validation(rows, append=True):
    """rows: list of dicts with keys in SUMMARY_COLS (missing keys default to "").
    Appends to validation_summary.csv; creates it with a header on first write of the run.
    Call once per script with ALL of that script's rows (simplest correct usage)."""
    exists = os.path.exists(VALIDATION_SUMMARY)
    mode = "a" if (append and exists) else "w"
    with open(VALIDATION_SUMMARY, mode, newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_COLS)
        if mode == "w":
            w.writeheader()
        for r in rows:
            out = {k: r.get(k, "") for k in SUMMARY_COLS}
            for k in ("reconstructed_value", "reference_value", "absolute_difference",
                      "percentage_difference"):
                if isinstance(out[k], (int, float)):
                    out[k] = _fmt_num(out[k])
            w.writerow(out)
    for r in rows:
        status = r.get("validation_status", "?")
        print(f"  [{status:16s}] {r['metric_id']:22s} recon={r.get('reconstructed_value')!s:>16} "
              f"ref={r.get('reference_value')!s:>16}  {r.get('explanation','')[:70]}")


def compare(metric_id, metric_name, recon, ref, reference_source, tolerance_pct=0.5,
            explanation_ok="Reconstruction matches the exported business view within tolerance.",
            explanation_diff=None):
    """Build one validation_summary.csv row comparing a reconstructed value to a reference value.
    tolerance_pct: percentage-difference threshold below which status is MATCH."""
    if recon is None or ref is None or (isinstance(ref, float) and pd.isna(ref)):
        return {
            "metric_id": metric_id, "metric_name": metric_name,
            "reconstructed_value": recon, "reference_value": ref,
            "absolute_difference": "", "percentage_difference": "",
            "validation_status": "NOT_DETERMINABLE", "reference_source": reference_source,
            "explanation": explanation_diff or "No reference value available for comparison.",
        }
    absdiff = abs(float(recon) - float(ref))
    pct = (absdiff / abs(float(ref)) * 100.0) if float(ref) != 0 else (0.0 if absdiff == 0 else float("inf"))
    status = "MATCH" if pct <= tolerance_pct else "DIFFERS"
    expl = explanation_ok if status == "MATCH" else (explanation_diff or "Reconstructed value differs from the exported view; see metric_reconstruction.md for the known mechanism.")
    return {
        "metric_id": metric_id, "metric_name": metric_name,
        "reconstructed_value": recon, "reference_value": ref,
        "absolute_difference": absdiff, "percentage_difference": pct,
        "validation_status": status, "reference_source": reference_source,
        "explanation": expl,
    }


def write_monthly(filename, df):
    os.makedirs(MONTHLY_DIR, exist_ok=True)
    path = os.path.join(MONTHLY_DIR, filename)
    df.to_csv(path, index=False)
    print(f"  wrote {path} ({len(df)} rows)")
    return path
