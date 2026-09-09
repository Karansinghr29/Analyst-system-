"""
Tests reversal-handling and soft-delete-handling correctness -- the two policies
business_reasoning_spec.md and semantic_layer.md are most explicit must never be implemented
"based only on intuition." Verifies the two conventions from engine.calculators.ledger produce
the PROVEN results already established in Phase E (validate_ledger.py LEDGER.01-08).
"""
from engine.calculators import ledger as L


class TestReversalHandling:
    def test_excl_and_incl_conventions_agree_on_ar_total(self):
        """conflicts.md C.002: reversal convention is proven immaterial to BALANCES."""
        excl = L.ledger_excl_reversals()
        incl = L.ledger_incl_reversals()
        ar_excl = excl[(excl["code"] == "1200") & (excl["party_kind"] == "tenant")]["signed_amount"].sum()
        ar_incl = incl[(incl["code"] == "1200") & (incl["party_kind"] == "tenant")]
        ar_incl_total = (ar_incl["debit"] - ar_incl["credit"]).sum()
        assert abs(ar_excl - ar_incl_total) < 0.01

    def test_excl_convention_drops_reversal_entries(self):
        excl = L.ledger_excl_reversals()
        assert excl["is_reversal_of"].notna().sum() == 0

    def test_excl_convention_drops_reversed_originals(self):
        excl = L.ledger_excl_reversals()
        incl = L.ledger_incl_reversals()
        reversed_ids = set(incl.loc[incl["is_reversal_of"].notna(), "is_reversal_of"].dropna())
        assert not (set(excl["journal_entry_id"]) & reversed_ids)

    def test_incl_convention_keeps_everything(self):
        excl = L.ledger_excl_reversals()
        incl = L.ledger_incl_reversals()
        assert len(incl) >= len(excl)

    def test_known_reversal_volume(self):
        """H.005: 14236 total journal_entries rows, 347 reversals (2.44%). Counted from
        journal_entries directly, NOT inferred from journal_lines -- 3 of the 14236 entries
        are 'stub' headers with ZERO lines (H.003/v_je_stub_pollution: source_table='manual'
        has empty_forward_je=3), so journal_lines.journal_entry_id.nunique() alone
        undercounts by exactly 3 (14233 vs 14236) -- found while writing this test, not a
        defect in the ledger reconstruction itself (which correctly has nothing to aggregate
        for a lineless entry)."""
        from engine.evidence_loader import load_table
        je = load_table("journal_entries")
        assert len(je) == 14236
        assert je["is_reversal_of"].notna().sum() == 347

        incl = L.ledger_incl_reversals()
        n_je_with_lines = incl["journal_entry_id"].nunique()
        assert n_je_with_lines == 14233  # 14236 - 3 stub entries, exact and explained

    def test_gross_turnover_differs_between_conventions(self):
        """H.007: 10 accounts show a nonzero excl-vs-incl gross-turnover difference, even
        though balances (above) are identical. Reversal convention IS material to turnover."""
        excl = L.ledger_excl_reversals()
        incl = L.ledger_incl_reversals()
        excl_debit = excl.groupby("code")["debit"].sum()
        incl_debit = incl.groupby("code")["debit"].sum()
        diff = (incl_debit - excl_debit).dropna()
        affected = diff[diff.abs() > 0.5]
        assert len(affected) == 10


class TestSoftDeleteHandling:
    def test_receipts_soft_delete_uses_is_deleted_flag(self):
        from engine.evidence_loader import load_table
        r = load_table("receipts")
        assert "is_deleted" in r.columns

    def test_expenses_has_no_soft_delete_concept(self):
        """business_logic.md 1.4 / 7: expenses has NO is_deleted column -- hard-delete only."""
        from engine.evidence_loader import load_table
        e = load_table("expenses")
        assert "is_deleted" not in e.columns

    def test_owner_payments_has_no_soft_delete_concept(self):
        from engine.evidence_loader import load_table
        op = load_table("owner_payments")
        assert "is_deleted" not in op.columns

    def test_tenant_allotments_has_no_soft_delete_concept(self):
        from engine.evidence_loader import load_table
        ta = load_table("tenant_allotments")
        assert "is_deleted" not in ta.columns

    def test_live_row_filtering_actually_excludes_deleted_receipts(self):
        """receipts (unlike invoices) contains a real mix: 5758 live + 100 soft-deleted --
        the meaningful case for proving the is_deleted filter has an actual effect."""
        from engine.evidence_loader import load_table
        r = load_table("receipts")
        live = r[r["is_deleted"].astype(str).str.lower() != "true"]
        assert len(r) == 5858
        assert len(live) == 5758
        assert len(r) - len(live) == 100

    def test_invoices_export_contains_no_soft_deleted_rows_at_all(self):
        """The exported invoices table happens to be 100% is_deleted=false already -- the
        filter is a no-op here, worth stating explicitly rather than assuming it behaves like
        receipts."""
        from engine.evidence_loader import load_table
        inv = load_table("invoices")
        assert len(inv) == 5214
        assert (inv["is_deleted"].astype(str).str.lower() == "false").all()
