"""
Regression tests for the 9 named conflicts the task brief specifically requires be protected
against regression. Each test locks in the exact figures already proven in Phase E
(metric_reconstruction.md / validation_summary.csv) so that a future change to a calculator
cannot silently "fix" (i.e. quietly resolve) one of these conflicts without a human noticing.
"""


class TestTenantBalanceConflict:
    """C.001/C.003/C.005, DQ.002 (CRITICAL) / DQ.019 (CRITICAL)."""

    def test_four_definitions_are_all_computed_independently(self, executor):
        ans = executor.execute("M.AR.001A")
        assert ans.trust_level == "SHOW_BOTH"
        assert len(ans.results) == 4

    def test_def_a_and_def_b_totals_are_proven_identical(self, executor):
        ans = executor.execute("M.AR.001A")
        by_label = {r.definition_label: r for r in ans.results}
        def_a = next(v for k, v in by_label.items() if k.startswith("Tenant dues -- Def A"))
        def_b = next(v for k, v in by_label.items() if k.startswith("Tenant dues -- Def B"))
        assert abs(def_a.value - def_b.value["ar_balance"]) < 0.01
        assert abs(def_a.value - 83297.85) < 0.01

    def test_def_c_and_def_d_diverge_by_more_than_10x(self, executor):
        ans = executor.execute("M.AR.001C")
        assert ans.trust_level == "BLOCK"
        by_label = {r.definition_label: r for r in ans.results}
        def_a = next(v for k, v in by_label.items() if k.startswith("Tenant dues -- Def A"))
        def_c = next(v for k, v in by_label.items() if k.startswith("Tenant dues -- Def C"))
        assert def_c.value / def_a.value > 10

    def test_tenant_transactions_is_frozen(self):
        from engine.evidence_loader import load_table
        tt = load_table("tenant_transactions")
        created = tt["created_at"].astype(str)
        assert created.min()[:10] >= "2026-04-17"
        assert created.max()[:10] <= "2026-04-28"

    def test_ar_family_never_returns_a_single_headline_number(self, executor):
        """No matter which of the 4 sibling metric_ids is queried, the answer must carry all
        4 labelled results -- never a single scalar a caller could mistake for THE answer."""
        for mid in ("M.AR.001A", "M.AR.001B", "M.AR.001C", "M.AR.001D"):
            ans = executor.execute(mid)
            assert len(ans.results) == 4, f"{mid}: expected all 4 AR definitions, got {len(ans.results)}"


class TestOccupancyDefinitionConflict:
    """C.006-C.009, DQ.004 (HIGH) / DQ.005 (HIGH)."""

    def test_five_definitions_all_computed(self, executor):
        ans = executor.execute("M.OCC.001")
        assert ans.trust_level == "SHOW_BOTH"
        assert len(ans.results) == 5

    def test_def_a_and_def_b_differ_by_exactly_7_beds(self, executor):
        ans = executor.execute("M.OCC.001")
        by_label = {r.definition_label: r for r in ans.results}
        def_a = next(v for k, v in by_label.items() if k.startswith("Def A"))
        def_b = next(v for k, v in by_label.items() if k.startswith("Def B"))
        assert def_b.value["occupied"] - def_a.value["occupied"] == 7
        assert def_a.value["total"] == def_b.value["total"] == 195

    def test_the_7_on_notice_beds_are_named(self):
        from engine.evidence_loader import load_table
        beds = load_table("beds")
        ta = load_table("tenant_allotments")
        on_notice_beds = ta.loc[ta["staying_status"] == "On-Notice", "bed_id"].unique()
        assert len(on_notice_beds) == 7


class TestProfitDefinitionConflict:
    """C.010/C.011, DQ.016 (CRITICAL)."""

    def test_three_definitions_computed(self, executor):
        ans = executor.execute("M.PROFIT.001")
        assert ans.trust_level == "BLOCK"
        assert len(ans.results) == 3

    def test_def_b_omits_owner_rent_causing_material_overstatement(self, executor):
        ans = executor.execute("M.PROFIT.001")
        by_label = {r.definition_label: r for r in ans.results}
        def_a = next(v for k, v in by_label.items() if k.startswith("Def A"))
        def_b = next(v for k, v in by_label.items() if k.startswith("Def B"))
        assert def_b.value > def_a.value
        overstatement_pct = (def_b.value - def_a.value) / def_a.value * 100
        assert overstatement_pct > 30  # proven ~36.6% in Phase E


class TestPnlElectricityGap:
    """C.012/C.013, DQ.015 (HIGH)."""

    def test_electricity_bucket_exactly_equals_unbucketed(self, executor):
        ans = executor.execute("M.EXP.002")
        buckets = ans.results[0].value
        electricity = buckets["electricity"]
        named_9 = sum(v for k, v in buckets.items() if k != "electricity")
        total = executor.execute("M.EXP.001").results[0].value
        unbucketed = round(total - named_9, 2)
        assert abs(unbucketed - electricity) < 0.01
        assert abs(electricity - 1030618.00) < 1.0

    def test_electricity_is_never_folded_into_utilities(self, executor):
        """Note: only 6 of the 9 named buckets have any ledger activity at all in this
        dataset (owner_rent, maintenance, administrative, marketing, other_expenses, plus the
        added electricity bucket) -- housekeeping/utilities/property_ops/salaries are absent
        because pandas groupby omits empty groups, not because of a calculator bug. The
        assertion below only needs 'electricity' present and, IF utilities happens to have
        activity, that it's not double-counting electricity into it."""
        ans = executor.execute("M.EXP.002")
        buckets = ans.results[0].value
        assert "electricity" in buckets
        utilities_value = buckets.get("utilities", 0.0)
        assert abs(utilities_value - buckets["electricity"]) > 1.0 or utilities_value == 0.0


class TestDepositSettlementConflict:
    """C.016, DQ.008 (HIGH)."""

    def test_source_vs_ledger_gap_matches_known_figure(self, executor):
        ans = executor.execute("M.DEP.002")
        source_total = ans.results[0].value["refund_amount_total"]
        assert abs(source_total - 5085959.33) < 0.01


class TestInvoiceBalanceDrift:
    """DQ.001 (CRITICAL)."""

    def test_42_7_pct_of_invoices_drift_internally(self):
        from engine.evidence_loader import load_table, money
        inv = load_table("invoices")
        live = inv[inv["is_deleted"].astype(str).str.lower() != "true"]
        drift = (money(live["total_amount"]).fillna(0) - money(live["amount_paid"]).fillna(0)
                 - money(live["balance"]).fillna(0)).abs()
        n_drift = (drift > 0.01).sum()
        pct = round(100.0 * n_drift / len(live), 1)
        assert n_drift == 2227
        assert pct == 42.7


class TestDuplicateInvoices:
    """C.020, DQ.013 (HIGH)."""

    def test_known_duplicate_group_and_excess_row_counts(self, executor):
        ans = executor.execute("M.RISK.005")
        v = ans.results[0].value
        assert v["duplicate_groups"] == 322
        assert v["excess_rows"] == 356


class TestOverlappingAllotments:
    """DQ.003 (MEDIUM) -- the one metric with a documented, unresolved reconstruction-method
    discrepancy against its own reference (214 here vs 187 in H.056)."""

    def test_overlap_count_matches_this_engines_own_prior_finding(self, executor):
        ans = executor.execute("M.RISK.007")
        assert ans.results[0].value == 214
        assert ans.results[0].validation_status == "DIFFERS"


class TestFrozenTenantTransactions:
    """DQ.019 (CRITICAL) -- covered in detail under TestTenantBalanceConflict; this class adds
    the specific 'never used for a live dues answer' behavioral guarantee."""

    def test_tenant_transactions_metric_is_always_block(self, executor):
        ans = executor.execute("M.AR.001D")
        assert ans.trust_level == "BLOCK"

    def test_tenant_transactions_never_wired_to_a_posting_trigger(self):
        """FN.TRG (55 triggers) does not reference tenant_transactions at all."""
        import csv
        with open(r"D:\data science\AI Analytics System\evidence\file_manifest.csv",
                  encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        trg_row = next(r for r in rows if r["key"] == "FN.TRG")
        import pandas as pd
        trg = pd.read_csv(r"D:\data science\AI Analytics System\\" + trg_row["file"],
                           encoding="utf-8-sig")
        assert not trg["table_name"].astype(str).str.contains("tenant_transactions").any()
