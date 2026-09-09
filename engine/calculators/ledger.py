"""
ledger.py -- shared ledger-reconstruction primitives.

Implements the two proven reversal conventions from business_logic.md 1.3 / conflicts.md C.002,
exactly as validated in scripts/validation/validate_ledger.py (8/8 checks MATCH). Every
ledger-derived calculator (revenue, expenses, profit, AR, deposits, cash, trial balance) builds
on these two functions rather than re-deriving reversal logic independently -- this is the
concrete mechanism that prevents "reversal logic based on intuition" (Phase D's own rule).
"""
from functools import lru_cache

import pandas as pd

from engine.evidence_loader import load_table, money, coa_accounts_str_code


def _base_frame():
    """journal_lines joined to coa_accounts (code as string), debit/credit coerced numeric.
    journal_lines is exported pre-denormalised with entry_date/is_reversal_of/source_table/
    source_id from journal_entries (data_inventory.md 5.1) -- no extra join needed for those."""
    jl = load_table("journal_lines")
    coa = coa_accounts_str_code()
    m = jl.merge(
        coa[["id", "code", "name", "account_type", "normal_balance"]].rename(columns={"id": "account_id"}),
        on="account_id", how="left",
    )
    m["debit"] = money(m["debit"]).fillna(0)
    m["credit"] = money(m["credit"]).fillna(0)
    return m


def _reversed_ids(jl):
    return set(jl.loc[jl["is_reversal_of"].notna(), "is_reversal_of"].dropna())


def signed_amount(frame):
    """signed_amount = CASE normal_balance WHEN 'DEBIT' THEN debit-credit ELSE credit-debit END
    -- business_logic.md 1.1, the v_account_balances sign convention."""
    return frame.apply(
        lambda r: (r["debit"] - r["credit"]) if r["normal_balance"] == "DEBIT" else (r["credit"] - r["debit"]),
        axis=1,
    )


@lru_cache(maxsize=1)
def _excl_cached():
    m = _base_frame()
    reversed_ids = _reversed_ids(m)
    excl = m[m["is_reversal_of"].isna() & ~m["journal_entry_id"].isin(reversed_ids)].copy()
    excl["signed_amount"] = signed_amount(excl)
    return excl


def ledger_excl_reversals():
    """The v_account_balances convention: reversal-EXCLUDED. Drops reversal entries AND any
    forward entry that has since been reversed. PROVEN equivalent in total to the included
    convention for balances (conflicts.md C.002); differs for gross turnover/counts. Cached --
    evidence is immutable within one process, and this join is re-used by every ledger-derived
    calculator (revenue, expenses, profit, AR, deposits, cash, trial balance)."""
    return _excl_cached().copy()


@lru_cache(maxsize=1)
def _incl_cached():
    m = _base_frame()
    m["signed_amount"] = signed_amount(m)
    return m


def ledger_incl_reversals():
    """Raw journal_lines, no reversal filter -- the v_tenant_current_dues /
    v_trial_balance_detailed convention. Reversal-INCLUDED; row counts are NOT reversal-neutral
    even though dollar totals are (business_logic.md 1.3). Cached, see ledger_excl_reversals."""
    return _incl_cached().copy()


def account_balance(account_code, party_kind=None, reversal="excl"):
    """SUM(signed_amount) for one account code, optionally filtered to a party_kind, under the
    requested reversal convention. Used by AR/deposit/cash calculators."""
    m = ledger_excl_reversals() if reversal == "excl" else ledger_incl_reversals()
    f = m[m["code"] == str(account_code)]
    if party_kind is not None:
        f = f[f["party_kind"] == party_kind]
    return f
