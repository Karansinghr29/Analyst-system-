"""
Phase 13: live data activation.

Offline tests never contact Supabase. The optional live class is skipped unless
AI_ANALYTICS_LIVE_TEST=true. That class must not print credentials.
"""
import json
import os
import urllib.request

import pytest

from engine.result import NOT_DETERMINABLE_TEXT
from engine.gate import TrustGate

from api import data_source as ds
from api.auth import suite_authenticator, bearer_headers
from api.security import RateLimiter, contains_secret_material, collect_configured_secrets
from api.live_connector import (
    SupabaseRestTransport, PostgresReadOnlyTransport, relation_from_logical,
    parse_content_range, assert_relation_allowed, PAGE_SIZE, _WRITE_SQL,
)
from api.live_replay import ManifestCsvTransport, values_equivalent, EXPECTED_SPECIAL_STATUSES
from api.owner_decisions import load_owner_decisions
from api.service import AnalyticsService, create_app


FREEZE = ds.EXPORT_SNAPSHOT_DATE


class _FakeResponse:
    def __init__(self, payload, headers):
        self._payload = payload
        self.headers = headers

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _PagedOpener:
    """PostgREST-shaped fake: honors Range and Prefer: count=exact."""

    def __init__(self, rows, page_size=2, omit_range=False, unknown_total=False,
                 truncate=False):
        self.rows = list(rows)
        self.page_size = page_size
        self.omit_range = omit_range
        self.unknown_total = unknown_total
        self.truncate = truncate
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append(req)
        assert req.get_method() == "GET"
        range_h = req.get_header("Range") or "0-999"
        start, end = [int(x) for x in range_h.split("-")]
        total = len(self.rows)
        chunk = self.rows[start:end + 1]
        if self.truncate and chunk and start != end:
            chunk = chunk[: max(0, len(chunk) - 1)]
        body = json.dumps(chunk).encode("utf-8")
        if self.omit_range:
            headers = {}
        elif self.unknown_total:
            last = start + len(chunk) - 1 if chunk else start
            headers = {"Content-Range": f"{start}-{last}/*"}
        elif total == 0:
            headers = {"Content-Range": "*/0"}
        else:
            last = start + len(chunk) - 1 if chunk else start
            headers = {"Content-Range": f"{start}-{last}/{total}"}
        return _FakeResponse(body, headers)


def test_parse_content_range_complete_and_empty():
    assert parse_content_range("0-999/33894") == (0, 999, 33894)
    assert parse_content_range("*/0") == (None, None, 0)
    with pytest.raises(ds.DataSourceError):
        parse_content_range("")
    with pytest.raises(ds.DataSourceError):
        parse_content_range("0-999/*")


def test_rest_paginates_until_reported_total():
    rows = [{"id": i, "v": i} for i in range(5)]
    t = SupabaseRestTransport(url="http://127.0.0.1:9", key="readonly-test-key",
                              opener=_PagedOpener(rows, page_size=2), page_size=2)
    got = t.fetch_table("public.journal_lines")
    assert [r["id"] for r in got] == [0, 1, 2, 3, 4]
    assert t.row_count("public.journal_lines") == 5


def test_rest_empty_table():
    t = SupabaseRestTransport(url="http://127.0.0.1:9", key="readonly-test-key",
                              opener=_PagedOpener([], page_size=2), page_size=2)
    assert t.fetch_table("public.beds") == []
    assert t.row_count("public.beds") == 0


def test_rest_refuses_missing_content_range():
    t = SupabaseRestTransport(url="http://127.0.0.1:9", key="readonly-test-key",
                              opener=_PagedOpener([{"id": 1}], omit_range=True), page_size=2)
    with pytest.raises(ds.DataSourceError):
        t.fetch_table("public.beds")


def test_rest_refuses_unknown_total():
    t = SupabaseRestTransport(url="http://127.0.0.1:9", key="readonly-test-key",
                              opener=_PagedOpener([{"id": 1}], unknown_total=True), page_size=2)
    with pytest.raises(ds.DataSourceError):
        t.fetch_table("public.beds")


def test_rest_refuses_truncated_page():
    t = SupabaseRestTransport(url="http://127.0.0.1:9", key="readonly-test-key",
                              opener=_PagedOpener([{"id": 1}, {"id": 2}, {"id": 3}],
                                                  page_size=2, truncate=True),
                              page_size=2)
    with pytest.raises(ds.DataSourceError):
        t.fetch_table("public.beds")


def test_rest_is_get_only_and_has_no_write():
    t = SupabaseRestTransport(url="http://127.0.0.1:9", key="k")
    assert not hasattr(t, "post")
    assert not hasattr(t, "write")
    assert not hasattr(SupabaseRestTransport, "insert")
    src = open(os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "api", "live_connector.py"), encoding="utf-8").read()
    assert "method=\"POST\"" not in src
    assert "method=\"PATCH\"" not in src
    assert "method=\"DELETE\"" not in src


def test_allowlist_refuses_non_evidence_and_non_public():
    with pytest.raises(ds.DataSourceError):
        assert_relation_allowed("auth.users")
    with pytest.raises(ds.DataSourceError):
        assert_relation_allowed("market.listings")
    schema, table = relation_from_logical("public.journal_lines")
    assert schema == "public" and table == "journal_lines"
    assert_relation_allowed("public.journal_lines")
    assert_relation_allowed("v_account_balances")


def test_service_role_key_is_refused(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-secret")
    with pytest.raises(ds.DataSourceError):
        SupabaseRestTransport(url="http://127.0.0.1:9", key="service-role-secret")


def test_as_of_must_be_the_export_freeze(registry):
    conn = ManifestCsvTransport()
    wrong = ds.LiveDataSource(name="probe", connection=conn, as_of="2026-09-02")
    report = ds.RevalidationHarness(registry).run(wrong)
    assert report.passed is False
    assert FREEZE in (report.remaining_requirement or report.notes)
    with pytest.raises(ds.QuarantineError):
        ds.bind_source(wrong, report)


def test_missing_as_of_still_fails(registry):
    live = ds.LiveDataSource(name="probe", connection=ManifestCsvTransport())
    d = live.descriptor()
    assert d.status == ds.STATUS_FAILED


def test_owner_decisions_are_read_only_and_default_empty():
    decisions = load_owner_decisions()
    assert decisions == ()
    src = open(os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "api", "owner_decisions.py"), encoding="utf-8").read()
    assert "open(" in src
    assert "\"w\"" not in src.replace("utf-8", "")
    assert "write(" not in src


def test_values_equivalent_policy():
    assert values_equivalent(1.00, 1.009)
    assert not values_equivalent(1.00, 2.00)
    assert values_equivalent({"occupied": 168, "total": 195}, {"total": 195, "occupied": 168})
    assert values_equivalent(None, None)


def test_special_baseline_statuses_are_documented():
    assert EXPECTED_SPECIAL_STATUSES["REV.02"] == "DIFFERS"
    assert EXPECTED_SPECIAL_STATUSES["PROFIT.02"] == "NOT_DETERMINABLE"


def test_export_backed_live_source_can_pass_and_bind(registry):
    """Exact-freeze simulator: live interface over the trusted CSVs. No network."""
    live = ds.LiveDataSource(name="csv-live", connection=ManifestCsvTransport(), as_of=FREEZE)
    report = ds.RevalidationHarness(registry).run(live)
    assert report.passed, (report.summary(), report.divergences[:8],
                           report.required_owner_decisions[:8], report.notes)
    assert report.checks_total == 80
    assert report.conflicts_total == 12
    assert report.dq_total == 32
    assert report.regression_total == 50
    assert report.regression_matched == 50
    bound = ds.bind_source(live, report)
    assert bound.descriptor().status == ds.STATUS_TRUSTED


def test_row_count_drift_stays_quarantined(registry):
    class Drift(ManifestCsvTransport):
        def row_count(self, logical_name):
            return super().row_count(logical_name) + 1
    live = ds.LiveDataSource(name="drift", connection=Drift(), as_of=FREEZE)
    report = ds.RevalidationHarness(registry).run(live)
    assert report.passed is False
    assert report.required_owner_decisions
    with pytest.raises(ds.QuarantineError):
        ds.bind_source(live, report)


def test_numeric_drift_is_not_waived_by_matching_trust(registry):
    class OneRow:
        def available(self):
            return True
        def fetch_table(self, logical_name, limit=None):
            return [{"id": 1, "balance_due": 99}]
        def row_count(self, logical_name):
            return 1
        def columns(self, logical_name):
            return ("id", "balance_due")
    live = ds.LiveDataSource(name="tiny", connection=OneRow(), as_of=FREEZE)
    report = ds.RevalidationHarness(registry).run(live)
    assert report.passed is False
    with pytest.raises(ds.QuarantineError):
        ds.bind_source(live, report)


def test_failed_live_leaves_export_serving(registry, tmp_path):
    svc = AnalyticsService(registry=registry, db_path=str(tmp_path / "p13.db"),
                           authenticator=suite_authenticator())
    h = svc.health()
    assert h["data_source"]["kind"] == "export"
    assert h["data_source"]["status"] == ds.STATUS_TRUSTED
    assert h["live_data"]["status"] in (ds.STATUS_UNAVAILABLE, ds.STATUS_QUARANTINED,
                                        ds.STATUS_FAILED)
    assert h["live_data"]["remaining_requirement"]
    gate = TrustGate(registry)
    assert gate.authorize("M.PROFIT.001").effective_level == "BLOCK"
    svc.close()


def test_supabase_url_is_treated_as_secret(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    secrets = collect_configured_secrets()
    assert "https://example.supabase.co" in secrets
    assert contains_secret_material("connect https://example.supabase.co now", extra_secrets=secrets)


def test_postgres_write_sql_still_refused():
    assert _WRITE_SQL.search("UPDATE journal_lines SET debit=0")
    pg = PostgresReadOnlyTransport(dsn="postgresql://unused")
    with pytest.raises(ds.DataSourceError):
        pg._execute("DELETE FROM journal_entries")


class TestPhase13Validator:
    def test_the_phase13_validator_passes(self):
        import subprocess, sys
        r = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                          "scripts", "validate_phase13_consistency.py")],
            capture_output=True, text=True)
        assert r.returncode == 0, (r.stdout or "")[-4000:] + (r.stderr or "")[-2000:]
        assert "No inconsistency" in (r.stdout or "")


@pytest.mark.skipif(os.environ.get("AI_ANALYTICS_LIVE_TEST") != "true",
                    reason="Live Supabase test requires AI_ANALYTICS_LIVE_TEST=true")
def test_real_supabase_roundtrip_if_explicitly_flagged(registry, tmp_path):
    """Does not print URL or keys. Missing credentials fail closed (quarantine), they do not skip."""
    live = ds.LiveDataSource.from_env(as_of=os.environ.get("AI_ANALYTICS_LIVE_AS_OF", ""))
    report = ds.RevalidationHarness(registry).run(live)
    if not live.available() or (live.as_of or "") != FREEZE:
        assert report.passed is False
        with pytest.raises(ds.QuarantineError):
            ds.bind_source(live, report)
        return
    if not report.passed:
        pytest.fail(f"live harness did not pass: {report.summary()} "
                    f"div={list(report.divergences)[:6]}")
    ds.bind_source(live, report)
    from engine.evidence_loader import bind_trusted_source, unbind_source
    bind_trusted_source(live)
    try:
        svc = AnalyticsService(registry=registry, db_path=str(tmp_path / "p13live.db"),
                               authenticator=suite_authenticator(), source=ds.ExportDataSource())
        # Service constructs its own live path from env; trust gate must still bind BLOCK.
        r = svc.ask("What's our profit?")
        assert r["trust_level"] == "BLOCK"
        assert r["headline_permitted"] is False
        svc.close()
    finally:
        unbind_source()
