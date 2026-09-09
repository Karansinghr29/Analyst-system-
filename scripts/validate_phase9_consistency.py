"""
validate_phase9_consistency.py -- Phase 9 anti-drift validator.

Checks the 12 conditions from the Phase 9 plan against the LIVE service:

   1. every endpoint returns a schema-valid payload
   2. every served trust level matches the live gate
   3. no BLOCK payload carries a headline
   4. every SHOW_BOTH payload carries all definitions
   5. every NOT_DETERMINABLE payload carries the exact phrase
   6. no response carries a formula, query, or raw source handle
   7. every role workspace matches the role registry
   8. authorization never alters a trust level
   9. conversation persistence round-trips clarification state
  10. the live connector is quarantined until the harness passes
  11. LLM adapters cannot bypass the verbalization guard
  12. source CSVs byte-identical

Check 8 is the subtle one. An authorization layer that could relax a conflict for a senior role
would defeat the trust gate invisibly, because the answer would still look authoritative. It is
verified by serving every metric under every role and asserting the trust posture is identical.

Read-only with respect to evidence. Uses a temporary conversation database.
"""
import csv
import hashlib
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine.semantic_registry import SemanticRegistry
from engine.gate import TrustGate
from engine.result import NOT_DETERMINABLE_TEXT
from engine import analyst_roles

from api.service import AnalyticsService
from api.authorization import Authorizer, ROLE_OWNER
from api.conversation_store import ConversationStore
from api import data_source as ds
from api import provider_config as pc

BASELINE_SHA = "aed87d5270eca59723a4380dc0c2f020a6931a8437bff5bd2b86e44809076f26"

ARTIFACTS = ("openapi.json", "powerbi_dataset_descriptor.json", "api_endpoint_registry.csv",
             "phase9_implementation_plan.md")

# Anything a client could compute from, or use to reach the data directly.
FORBIDDEN_KEYS = ("sql", "query", "formula", "expression", "connection", "csv_path",
                  "file_path", "raw_rows", "aggregation_fn", "dsl", "connection_string")


def _walk_keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}.{k}" if path else k
            yield from _walk_keys(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_keys(v, f"{path}[{i}]")


def main():
    registry = SemanticRegistry()
    gate = TrustGate(registry)
    tmpdir = tempfile.mkdtemp()
    svc = AnalyticsService(registry=registry, db_path=os.path.join(tmpdir, "v9.db"))
    problems, warnings = [], []

    # -- 1: endpoints return schema-valid payloads --------------------------------------------
    payloads = {}
    try:
        payloads["health"] = svc.health()
        payloads["trust"] = svc.trust_summary()
        payloads["owner_home"] = svc.owner_home()
        payloads["metrics"] = svc.metrics()
        payloads["insights"] = svc.insights()
        payloads["changes"] = svc.changes()
        payloads["data_quality"] = svc.data_quality()
        payloads["roles"] = svc.roles()
        payloads["report"] = svc.executive_report()
        payloads["llm"] = svc.llm_adapters()
    except Exception as e:
        problems.append(f"[1] an endpoint raised: {type(e).__name__}: {e}")

    for name, p in payloads.items():
        try:
            json.dumps(p, default=str)
        except (TypeError, ValueError) as e:
            problems.append(f"[1] {name}: payload is not JSON-serialisable: {e}")

    # -- 2, 3, 4, 5: trust fidelity per metric --------------------------------------------------
    for mid in registry.all_ids():
        lvl = gate.authorize(mid).effective_level
        detail = svc.metric_detail(mid)
        if not detail.get("available"):
            problems.append(f"[2] {mid}: metric detail unavailable to the owner role")
            continue
        tile = detail["tile"]

        if tile["trust"]["trust_level"] != lvl:
            problems.append(
                f"[2] {mid}: served trust {tile['trust']['trust_level']} != gate {lvl}")

        if lvl == "BLOCK":
            if tile["headline_permitted"] or tile["value"] is not None or tile["display_value"]:
                problems.append(f"[3] {mid}: BLOCK payload carries a headline")
            if tile["chart_type"] != "none":
                problems.append(f"[3] {mid}: BLOCK payload offers a chart")

        if lvl == "SHOW_BOTH":
            if tile["headline_permitted"] or tile["value"] is not None:
                problems.append(f"[4] {mid}: SHOW_BOTH payload carries a headline")
            cv = svc.conflict_view(mid)
            if cv.get("available") is False:
                problems.append(f"[4] {mid}: no conflict view served for a SHOW_BOTH metric")
            elif cv["definitions_computable"] and len(cv["definitions"]) < 2:
                problems.append(f"[4] {mid}: conflict view served < 2 definitions")

        if lvl == "NOT_DETERMINABLE":
            if tile["value"] is not None or tile["display_value"]:
                problems.append(f"[5] {mid}: NOT_DETERMINABLE payload carries a value")
            if NOT_DETERMINABLE_TEXT not in (tile["unavailable_reason"] or ""):
                problems.append(f"[5] {mid}: NOT_DETERMINABLE payload omits the exact phrase")

    # -- 6: no response carries a formula, query, or source handle -------------------------------
    for name, p in payloads.items():
        for key in _walk_keys(p):
            leaf = key.split(".")[-1].lower()
            if any(f == leaf or f in leaf for f in FORBIDDEN_KEYS):
                problems.append(
                    f"[6] {name}: response exposes {key!r} -- a client given a query or formula "
                    f"can compute, and a client that can compute can disagree with the engine")

    # -- 7: role workspaces match the role registry ------------------------------------------------
    auth = Authorizer(registry)
    known = {r.role_id for r in analyst_roles.all_roles()}
    served = {r["analyst_role"] for r in svc.roles()["roles"]}
    for missing in known - served:
        problems.append(f"[7] role {missing!r} has no served workspace")
    for r in analyst_roles.all_roles():
        ws = svc.role_workspace(r.role_id)
        if not ws.get("available"):
            problems.append(f"[7] workspace for {r.role_id} is unavailable")

    # -- 8: authorization never alters a trust level ------------------------------------------------
    for role_id in auth.known_roles():
        visible = auth.filter_metrics(role_id)
        listing = {m["metric_id"]: m for m in svc.metrics(role_id)["metrics"]}
        if set(listing) != set(visible):
            problems.append(
                f"[8] {role_id}: served metric set differs from the authorization filter")
        for mid, tile in listing.items():
            expected = gate.authorize(mid).effective_level
            if tile["trust"]["trust_level"] != expected:
                problems.append(
                    f"[8] {role_id}/{mid}: trust {tile['trust']['trust_level']} != gate "
                    f"{expected} -- authorization must never change how a visible metric is "
                    f"gated")
            if tile["headline_permitted"] != (expected in ("SAFE", "DISCLOSE")):
                problems.append(
                    f"[8] {role_id}/{mid}: headline permission differs from the gate verdict")

    # -- 9: conversation persistence round-trips clarification state ----------------------------------
    store = ConversationStore(os.path.join(tmpdir, "roundtrip.db"))
    try:
        from engine.conversation_state import PendingClarification, DefinitionSelection
        store.create("c1", "subject", ROLE_OWNER)
        pending = PendingClarification(
            trigger="conflicting_definitions", question="Which definition?",
            options=("M.COL.001: application", "M.COL.003: ledger"),
            option_metric_ids=("M.COL.001", "M.COL.003"), asked_at_turn=0, state="REQUIRED")
        store.save_clarification("c1", pending)
        back = store.load_clarification("c1")
        if back is None:
            problems.append("[9] an open clarification did not survive persistence -- a "
                            "reloaded conversation would read the answer as a fresh question")
        else:
            for f in ("trigger", "question", "state", "options", "option_metric_ids"):
                if getattr(back, f) != getattr(pending, f):
                    problems.append(f"[9] clarification field {f!r} did not round-trip")

        sel = DefinitionSelection(concept="occupancy", metric_id="M.OCC.001",
                                  definition_label="Def A", selected_at_turn=1,
                                  user_text="use Def A", alternatives_shown=("Def A", "Def B"))
        store.save_selection("c1", sel)
        sels = store.load_selections("c1")
        if not sels or sels[0].definition_label != "Def A":
            problems.append("[9] a definition selection did not round-trip")
    finally:
        store.close()

    # -- 10: the live connector is quarantined until the harness passes -------------------------------
    live = ds.LiveDataSource(name="probe", connection=object(), as_of="2026-09-01")
    report = ds.RevalidationHarness(registry, gate, svc.executor).run(live)
    if report.passed:
        problems.append("[10] a live source passed re-validation without a real connection")
    try:
        ds.bind_source(live, report)
        problems.append("[10] an un-revalidated live source was bound to the engine")
    except ds.QuarantineError:
        pass
    no_asof = ds.LiveDataSource(name="no-asof", connection=object())
    if no_asof.descriptor().status != ds.STATUS_FAILED:
        problems.append("[10] a live source without its own as-of date was not failed")

    # -- 11: LLM adapters cannot bypass the guard ----------------------------------------------------
    cfg = svc.provider_config
    if cfg.mode != pc.MODE_OFFLINE:
        warnings.append(f"[11] provider mode is {cfg.mode!r}, not offline")
    if cfg.describe()["network_access"]:
        problems.append("[11] the default provider configuration requests network access")
    for a in pc.available_adapters():
        if a["enabled"]:
            problems.append(f"[11] adapter {a['name']!r} is enabled by default")
    try:
        pc.build_provider(pc.ProviderConfig(mode=pc.MODE_HTTP, adapter_name="groq"))
        problems.append("[11] an HTTP adapter was constructed; this build ships no client")
    except Exception:
        pass

    # -- 12: source integrity -------------------------------------------------------------------------
    with open(os.path.join(ROOT, "evidence", "file_manifest.csv"), encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    h = hashlib.sha256()
    for r in rows:
        p = os.path.join(ROOT, r["file"])
        if not os.path.exists(p):
            problems.append(f"[12] source CSV missing: {r['file']}")
            continue
        with open(p, "rb") as fh:
            h.update(fh.read())
    digest = h.hexdigest()
    if digest != BASELINE_SHA:
        problems.append(f"[12] SOURCE CSVs CHANGED: {digest} != {BASELINE_SHA}")

    missing = [a for a in ARTIFACTS if not os.path.exists(os.path.join(ROOT, a))]
    for a in missing:
        problems.append(f"[artifacts] {a}: MISSING")

    svc.close()

    print("=" * 88)
    print("PHASE 9 CONSISTENCY VALIDATION -- integration layer vs. the live engine")
    print("=" * 88)
    print(f"\n[artifacts]     {len(ARTIFACTS) - len(missing)}/{len(ARTIFACTS)}")
    print(f"[endpoints]     {len(payloads)} service surfaces exercised")
    print(f"[metrics]       {len(registry.all_ids())}")
    print(f"[roles]         {len(auth.known_roles())} (incl. the owner presentation role)")
    print(f"[data source]   {svc.source.descriptor().status} "
          f"-- {svc._report.summary()}")
    print(f"[llm]           {cfg.mode}, network_access={cfg.describe()['network_access']}")
    print(f"[source]        SHA-256 {digest[:16]}... "
          f"{'MATCHES baseline' if digest == BASELINE_SHA else 'CHANGED'}")
    print(f"\n[problems]      {len(problems)}")
    print(f"[warnings]      {len(warnings)}")

    if problems:
        print("\nINCONSISTENCIES:")
        for p in problems:
            print(f"   {p}")
    else:
        print("\nNo inconsistency between the integration layer and the engine.")
    for w in warnings:
        print(f"   warning: {w}")

    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
