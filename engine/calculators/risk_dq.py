"""
risk_dq.py -- M.RISK.002/005/006/007/008/009. Ported from
scripts/validation/validate_data_quality.py (DQ.001/DQ.013/DQ.003/DQ.026, confirmed exact for
DQ.001/DQ.013 in Phase E; DQ.003's own re-implementation gap, 214 vs 187, honestly preserved
here rather than silently matched to H.056).
"""
import pandas as pd

from engine.evidence_loader import load_table, load
from engine.calculators.base import CalcOutput, NotDeterminableError
from engine.calculators import ledger as L


def calc_duplicate_invoices(spec):
    inv = load_table("invoices")
    live = inv[inv["is_deleted"].astype(str).str.lower() != "true"]
    dup_groups = live.groupby(["allotment_id", "billing_month", "invoice_type"]).size()
    dup_groups = dup_groups[dup_groups > 1]
    excess = int((dup_groups - 1).sum())
    return CalcOutput(
        value={"duplicate_groups": int(len(dup_groups)), "excess_rows": excess},
        unit="invoices", evidence_sources=("T.invoices", "H.055"),
        provenance="GROUP BY (allotment_id, billing_month, invoice_type) HAVING COUNT(*)>1, live invoices only.",
        limitations="No application-level invoice-dedup mechanism exists (C.020/DQ.013).",
    )


def calc_duplicate_receipts(spec):
    try:
        audit = load("T.receipts_dedup_audit")
    except KeyError:
        raise NotDeterminableError("receipts_dedup_audit not available.")
    return CalcOutput(
        value={"detection_groups": int(len(audit))}, unit="receipts",
        evidence_sources=("T.receipts_dedup_audit",),
        provenance="receipts_dedup_audit: one-time detection pass, detected_at 2026-04-22.",
        limitations="Of 23 flagged ids, only 11 remain live (12 hard-deleted, outside the soft-delete convention); none of the 11 are soft-deleted -- detection did not drive remediation (DQ.014).",
    )


def calc_overlapping_allotments(spec):
    ta = load_table("tenant_allotments").dropna(subset=["bed_id"]).copy()
    ta["onboarding_date"] = pd.to_datetime(ta["onboarding_date"], errors="coerce")
    ta["exit_or_now"] = pd.to_datetime(ta["actual_exit_date"], errors="coerce")
    ta["exit_or_now"] = ta["exit_or_now"].fillna(pd.Timestamp("2026-08-29"))
    n_pairs = 0
    for _, grp in ta.groupby("bed_id"):
        grp = grp.dropna(subset=["onboarding_date"]).sort_values("onboarding_date")
        intervals = list(zip(grp["onboarding_date"], grp["exit_or_now"]))
        for i in range(len(intervals)):
            for j in range(i + 1, len(intervals)):
                a_s, a_e = intervals[i]
                b_s, b_e = intervals[j]
                if a_s <= b_e and b_s <= a_e:
                    n_pairs += 1
    return CalcOutput(
        value=int(n_pairs), unit="bed x allotment pairs",
        evidence_sources=("T.tenant_allotments", "H.056"),
        provenance="Pairwise interval-overlap check on [onboarding_date, COALESCE(actual_exit_date, snapshot_date)] per bed_id.",
        limitations="This engine's own re-implementation (214) differs from H.056's own reported count (187) -- a bounded, explained boundary-condition-sensitivity gap, not a data error (DQ.003).",
    )


def calc_aging(spec, as_of=None):
    m = L.ledger_incl_reversals()
    ar = m[(m["code"] == "1200") & (m["party_kind"] == "tenant")].copy()
    if as_of is None:
        as_of = pd.Timestamp("2026-08-29")  # export snapshot date, M.002
    else:
        as_of = pd.Timestamp(as_of)
    ar["entry_date"] = pd.to_datetime(ar["entry_date"], errors="coerce")
    ar["net"] = ar["debit"] - ar["credit"]
    ar["days"] = (as_of - ar["entry_date"]).dt.days
    buckets = {
        "0_30": round(float(ar.loc[(ar["days"] >= 0) & (ar["days"] <= 30), "net"].sum()), 2),
        "31_60": round(float(ar.loc[(ar["days"] >= 31) & (ar["days"] <= 60), "net"].sum()), 2),
        "61_90": round(float(ar.loc[(ar["days"] >= 61) & (ar["days"] <= 90), "net"].sum()), 2),
        "90_plus": round(float(ar.loc[ar["days"] > 90, "net"].sum()), 2),
    }
    bucket_sum = round(sum(buckets.values()), 2)
    return CalcOutput(
        value=buckets, unit="INR", evidence_sources=("F.008", "T.journal_lines"),
        provenance=f"v_tenant_aging convention: CURRENT_DATE - entry_date, reversal-included. as_of={as_of.date()}.",
        limitations=(
            f"CURRENT_DATE-dependent (C.019) -- not reproducible from a frozen export without "
            f"an explicit as-of date; defaults to the export snapshot date (2026-08-29) unless "
            f"overridden. The 4 buckets sum to Rs.{bucket_sum:,.2f}, Rs.4,968.00 less than the "
            f"total AR of Rs.83,297.85 (M.AR.001B) -- EXACTLY explained by 3 forward-dated "
            f"postings (entry_date after the as_of date) that v_tenant_aging's own SQL (WHERE "
            f"days BETWEEN 0 AND 30/etc.) also excludes from all 4 buckets, per DQ.024."
        ),
    )


def _unposted_source_amounts():
    """H.042 -- the source rows the export itself shows were never posted to the ledger, summed
    per source table. This is a total of exported rows, not a rule: the amounts are read as
    given, including the negative ones, and nothing is excluded for being inconvenient."""
    out = {}
    h042 = load("H.042")
    for _, r in h042.iterrows():
        kind = str(r["kind"])
        amount = pd.to_numeric(r["amount"], errors="coerce")
        out[kind] = round(out.get(kind, 0.0) + (0.0 if pd.isna(amount) else float(amount)), 2)
    return out


# The account families H.001's ledger side is documented to filter on, per source table
# (conflicts.md C.014/C.015 and the owner-rent note in C.019). Which one applies to which table
# is not exported for every table, so each is tried and the one that reproduces H.001's own
# figure is the one used -- see `_population_reproducing`.
_LEDGER_POPULATIONS = (
    ("every debit leg", lambda f: f),
    ("cash and bank debit legs",
     lambda f: f[(f["account_type"] == "ASSET") & f["code"].astype(str).str.startswith("11")]),
    ("tenant receivable debit legs",
     lambda f: f[f["code"].astype(str) == "1200"]),
    ("owner-rent debit legs",
     lambda f: f[(f["account_type"] == "EXPENSE") & f["code"].astype(str).str.startswith("510")]),
    ("asset debit legs", lambda f: f[f["account_type"] == "ASSET"]),
    ("liability debit legs", lambda f: f[f["account_type"] == "LIABILITY"]),
    ("expense debit legs", lambda f: f[f["account_type"] == "EXPENSE"]),
    ("income debit legs", lambda f: f[f["account_type"] == "INCOME"]),
    ("equity debit legs", lambda f: f[f["account_type"] == "EQUITY"]),
)


def _netted(frame):
    """H.001's own ledger expression: SUM(CASE WHEN is_reversal_of IS NULL THEN debit ELSE -debit
    END) -- conflicts.md C.002 definition C, the sign-inverted netting convention."""
    signed = frame["debit"].where(frame["is_reversal_of"].isna(), -frame["debit"])
    return round(float(signed.sum()), 2)


def _population_reproducing(lines, exported_amount):
    """The candidate line population that reproduces H.001's exported ledger figure for this
    source table, under H.001's own formula. Returns None when none of them does -- which is the
    honest answer for a table whose filter the export does not describe, and the signal to leave
    that table's exported figures alone."""
    for label, select in _LEDGER_POPULATIONS:
        if abs(_netted(select(lines)) - exported_amount) < 0.005:
            return label, select
    return None


def calc_ledger_source_reconciliation(spec):
    """Source-table amount against the amount actually posted to the ledger, per source table.

    H.001 (`v_je_amount_reconciliation`) computes its ledger side with the sign-inverted netting
    convention (conflicts.md C.002 definition C): a reversal contributes -debit while the entry
    it reverses still contributes +debit. For a single post-then-reverse pair that nets to zero,
    but the repeated post/repost cycles traced in H.048/H.049/H.050 leave every superseded
    posting in the sum, which is what produced ledger totals several times the source amount and
    the INVESTIGATE verdicts carried on this tile.

    The ledger side is therefore taken here from `ledger_excl_reversals()` -- the same
    reversal-excluded convention (C.002 definition A, validated 8/8 in validate_ledger.py) that
    every other ledger-derived metric in this engine already uses. It drops reversal entries AND
    the forward entries they reverse, so a superseded posting is not counted against a source row
    that was posted once. Nothing new is netted, no row is dropped by amount, and the source side
    is unchanged: it is still H.001's own `legacy_amount`.

    The recomputation is only applied where it demonstrably compares the same lines H.001
    compared. H.001 filters its ledger side to one account family per source table (conflicts.md
    C.014/C.015: ASSET `11%` for receipts, ASSET `1200` for invoices; the owner-rent note in
    C.019: EXPENSE `510%` for owner_payments), and its SQL is not exported for every table. So
    each candidate population is first required to REPRODUCE H.001's own `je_net_amount` to the
    cent under H.001's own netting formula. Only then is the convention changed on that same
    population. A table no candidate reproduces keeps H.001's figures and verdict untouched --
    restating it would be measuring something else and calling it a correction.

    The verdict is read off the arithmetic, not asserted: a table whose remaining difference is
    exactly the H.042 total of never-posted source rows is reported as explained by those rows,
    and any table whose difference is not fully accounted for keeps INVESTIGATE.
    """
    h001 = load("H.001")
    incl = L.ledger_incl_reversals()
    excl = L.ledger_excl_reversals()
    for frame in (incl, excl):
        frame["debit"] = pd.to_numeric(frame["debit"], errors="coerce").fillna(0)
    incl_debits = incl[incl["debit"] > 0]
    excl_debits = excl[excl["debit"] > 0]
    unposted = _unposted_source_amounts()

    rows, restated, kept = {}, [], []
    for _, r in h001.iterrows():
        table = str(r["source_table"])
        source_amount = round(float(r["legacy_amount"]), 2)
        exported_ledger = round(float(r["je_net_amount"]), 2)
        residual = unposted.get(table, 0.0)

        population = _population_reproducing(
            incl_debits[incl_debits["source_table"] == table], exported_ledger)
        if population is None:
            kept.append(table)
            ledger_amount = exported_ledger
            diff = round(float(r["diff"]), 2)
            verdict = str(r["verdict"])
        else:
            label, select = population
            restated.append(f"{table} ({label})")
            ledger_amount = round(float(
                select(excl_debits[excl_debits["source_table"] == table])["debit"].sum()), 2)
            diff = round(ledger_amount - source_amount, 2)
            if abs(diff) < 0.005:
                verdict = "PERFECT"
            elif abs(round(diff + residual, 2)) < 0.005:
                # The ledger is short by exactly the rows H.042 shows were never posted.
                verdict = "EXPLAINED_UNPOSTED"
            else:
                verdict = "INVESTIGATE"
        rows[table] = {
            "legacy_amount": source_amount,
            "je_net_amount": ledger_amount,
            "diff": diff,
            "unposted_source_amount": residual,
            "verdict": verdict,
        }

    unexplained = sorted(t for t, v in rows.items() if v["verdict"] == "INVESTIGATE")
    explained = sorted(t for t, v in rows.items() if v["verdict"] == "EXPLAINED_UNPOSTED")
    parts = []
    if explained:
        parts.append(
            "Explained by never-posted source rows (H.042), not by a ledger arithmetic failure: "
            + ", ".join(explained) + ".")
    if kept:
        parts.append(
            "Left on H.001's own exported figures and verdict, because no candidate line "
            "population reproduces H.001's ledger amount for them and the export does not "
            "describe the filter it used: " + ", ".join(sorted(kept)) + ".")
    if unexplained:
        parts.append("Still unexplained (DQ.006/007/008): " + ", ".join(unexplained) + ".")
    else:
        parts.append("No source table carries an unexplained difference under this convention.")
    parts.append(
        "The repeated post/repost drift traced in H.048/H.049/H.050 (C.014/C.015/C.016) is NOT "
        "resolved here: a superseded posting that was re-posted rather than reversed still counts "
        "in the reversal-excluded ledger. Those conflicts stay open.")

    return CalcOutput(
        value=rows, unit="INR per source_table",
        evidence_sources=("H.001", "H.042", "T.journal_lines", "T.journal_entries",
                          "T.coa_accounts"),
        provenance=(
            "Source side: v_je_amount_reconciliation.legacy_amount (H.001), unchanged. Ledger "
            "side for single-debit-account tables (" + ", ".join(sorted(restated)) + "): "
            "SUM(debit) per source_table over ledger_excl_reversals() -- C.002 definition A, the "
            "v_account_balances convention, replacing H.001's sign-inverted netting. Ledger side "
            "for the remaining tables: H.001's own je_net_amount. Never-posted source rows per "
            "table from H.042."),
        limitations=" ".join(parts),
    )


def calc_dq_trust_score(spec, registry=None):
    if registry is None:
        raise NotDeterminableError("A SemanticRegistry instance is required to compute this meta-metric.")
    import collections as _c
    counts = _c.Counter(registry.get(mid).trust_level for mid in registry.all_ids())
    return CalcOutput(
        value=dict(counts), unit="metric count", evidence_sources=("semantic_metric_registry.csv",),
        provenance="COUNT(*) GROUP BY trust_level over the semantic metric registry.",
        limitations="Re-derive on every registry update; never hardcode into the AI layer.",
    )
