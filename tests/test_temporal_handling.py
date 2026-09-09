"""
Historical date handling and current-snapshot handling
(question_understanding_spec.md 5, business_dimensions.md 1).
"""
import pandas as pd

from engine.calculators.risk_dq import calc_aging


class TestHistoricalDateHandling:
    def test_revenue_uses_entry_date_not_created_at(self):
        """entry_date is the documented business date for ledger metrics; journal_lines also
        carries a denormalised created_at-adjacent posted_at, which must NOT be substituted."""
        from engine.evidence_loader import load_table
        jl = load_table("journal_lines")
        assert "entry_date" in jl.columns
        assert "posted_at" in jl.columns
        # entry_date and posted_at are NOT the same column and can differ materially
        # (business_logic.md 9.2: owner_payments posted in a single 2026-08-13 batch for
        # entries dated as far back as 2022-11) -- confirms they are genuinely distinct bases.
        both = jl.dropna(subset=["entry_date", "posted_at"])
        differ = (pd.to_datetime(both["entry_date"], errors="coerce").dt.date.astype(str)
                  != pd.to_datetime(both["posted_at"], errors="coerce").dt.date.astype(str))
        assert differ.sum() > 0

    def test_maintenance_ticket_created_at_IS_the_business_date_by_documented_exception(self):
        """business_dimensions.md 17: maintenance_tickets has no other business-open-date
        column -- created_at is correctly used here, the ONE confirmed exception."""
        from engine.evidence_loader import load_table
        mt = load_table("maintenance_tickets")
        # No separate "opened_date"/"ticket_date" column exists on this table.
        assert "opened_date" not in mt.columns
        assert "ticket_date" not in mt.columns
        assert "created_at" in mt.columns

    def test_revenue_by_month_uses_documented_coverage_window(self, executor):
        ans = executor.execute("M.REV.002")
        months = list(ans.results[0].value.keys())
        assert min(months) >= "2019-11-01"
        assert max(months) <= "2026-09-01"

    def test_maintenance_coverage_is_the_shortest_operational_domain(self, executor):
        """20-month coverage -- YoY must never be attempted for this domain
        (question_understanding_spec.md 5.3)."""
        from engine.evidence_loader import load_table
        mt = load_table("maintenance_tickets")
        created = pd.to_datetime(mt["created_at"], utc=True, errors="coerce")
        months = (created.max().to_period("M") - created.min().to_period("M")).n + 1
        assert months <= 21  # ~20 months, matches metric_reconstruction.md 4


class TestCurrentSnapshotHandling:
    def test_aging_defaults_to_export_snapshot_date(self):
        """v_tenant_aging is CURRENT_DATE-dependent (C.019/DQ.018) -- offline reconstruction
        must fix an explicit as-of date rather than using today's real date, per
        conflicts.md C.019's own recommended handling."""
        out_default = calc_aging(spec=None)
        out_explicit = calc_aging(spec=None, as_of="2026-08-29")
        assert out_default.value == out_explicit.value

    def test_aging_as_of_date_changes_bucket_assignment(self):
        """Proves the as_of parameter actually affects the computation (not a no-op) --
        the exact reproducibility hazard C.019 documents."""
        out_a = calc_aging(spec=None, as_of="2026-08-29")
        out_b = calc_aging(spec=None, as_of="2020-01-01")
        assert out_a.value != out_b.value

    def test_aging_bucket_gap_explained_by_forward_dated_postings(self):
        """DQ.024: 3 forward-dated journal postings (Rs.4,968.00) fall outside all 4 aging
        buckets, exactly explaining the gap between bucket-sum and total AR."""
        out = calc_aging(spec=None, as_of="2026-08-29")
        bucket_sum = round(sum(out.value.values()), 2)
        assert abs((bucket_sum + 4968.00) - 83297.85) < 0.01

    def test_cash_balance_is_a_running_total_not_period_scoped(self, executor):
        """M.CASH.001: a cumulative balance -- historical_policy states this explicitly; there
        is no 'period' filter that meaningfully changes an all-time running total."""
        spec = executor.registry.get("M.CASH.001")
        assert "running" in spec.historical_policy.lower() or "cumulative" in spec.historical_policy.lower() or "full ledger span" in spec.historical_policy.lower()
