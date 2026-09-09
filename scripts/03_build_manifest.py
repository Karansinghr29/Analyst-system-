import csv, json, os, collections

base = r"D:\data science\AI Analytics System"
SP = r"C:\Users\Vishful1\AppData\Local\Temp\claude\D--data-science-AI-Analytics-System\7f222bb7-4659-4eed-96de-3c93b616fc89\scratchpad"
os.chdir(base)
csv.field_size_limit(2**31 - 1)


def rd(p):
    with open(p, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


tabsig = {k: set(v) for k, v in json.load(open(os.path.join(SP, 'tabsig.json'))).items()}
rc = json.load(open(os.path.join(SP, 'rowcounts.json')))
vcols = collections.defaultdict(set)
for r in rd("Supabase Snippet Untitled query (17).csv"):
    vcols[r['schema_name'] + "." + r['view_name']].add(r['column_name'])
fp = json.load(open(os.path.join(SP, 'fingerprints.json')))
with open('..csv', encoding='utf-8-sig', newline='') as f:
    rr = list(csv.reader(f))
fp.append({'file': '..csv', 'bytes': 93, 'cols': rr[0], 'ncols': 3, 'rows': 1})

Q = "Supabase Snippet Untitled query"
T = "Supabase Snippet Untitled query - 2026-08-29T"

META = {
 Q + ".csv": ("M.000", "schema_scope", "Schema in/out-of-scope inventory: public=131 tables/54 views, market=17 tables"),
 Q + " (1).csv": ("M.001", "object_presence_check", "58 expected objects, all PRESENT"),
 Q + " (2).csv": ("M.002", "snapshot_start", "Snapshot START 2026-08-29 09:02:03.620Z txn 421016"),
 Q + " (3).csv": ("M.003", "object_inventory", "148 in-scope base tables: relkind, size, live/dropped cols"),
 Q + " (4).csv": ("M.004", "column_inventory", "1897 columns: type, nullable, default, enum/array"),
 Q + " (5).csv": ("M.005", "dropped_columns", "44 dropped-column slots"),
 Q + " (6).csv": ("M.006", "row_counts_exact", "148 exact counts, counted_at 2026-08-29 09:02:53.218Z"),
 Q + " (7).csv": ("M.007", "organization_grain", "122 tables with organization_id; null-org rows"),
 Q + " (8).csv": ("M.008", "constraints", "565 constraints PK/UK/FK/CHECK"),
 Q + " (9).csv": ("M.009", "foreign_keys", "322 declared FKs with on_delete/on_update"),
 Q + " (10).csv": ("M.010", "implied_fks", "90 undeclared/implied relationships"),
 Q + " (11).csv": ("M.011", "polymorphic_refs", "5 polymorphic discriminator/reference pairs"),
 Q + " (12).csv": ("M.012", "json_columns", "11 JSON/JSONB columns"),
 Q + " (13).csv": ("M.013", "enum_values", "38 enum values"),
 Q + " (14).csv": ("M.014", "enum_columns", "13 enum-typed columns"),
 Q + " (15).csv": ("M.015", "indexes", "428 indexes"),
 Q + " (16).csv": ("M.016", "view_definitions", "54 public view SQL definitions"),
 Q + " (17).csv": ("M.017", "view_columns", "749 view columns"),
 Q + " (18).csv": ("M.018", "view_dependencies", "148 view -> object dependency edges"),
 Q + " (19).csv": ("M.019", "routine_inventory_full", "483 in-scope routines, signature only"),
 Q + " (20).csv": ("M.020", "routine_definitions_a", "36 routine definitions"),
 Q + " (21).csv": ("M.021", "trigger_wiring_dup", "55 triggers - EXACT DUPLICATE of FN.TRG"),
 Q + " (22).csv": ("M.022", "routine_definitions_b", "40 function definitions"),
 Q + " (23).csv": ("M.023", "column_profile", "1891 cols: total/non-null/distinct"),
 Q + " (24).csv": ("M.024", "numeric_profile", "267 numeric cols: min/max/avg/neg/zero/monetary flag"),
 Q + " (25).csv": ("M.025", "temporal_profile", "296 date cols: min/max/months/before2019/after_today"),
 Q + " (26).csv": ("M.026", "generated_sql_helper", "Generated profiling SQL - NOT data"),
 Q + " (27).csv": ("M.027", "sensitive_columns", "160 PII/sensitive columns + export action"),
 T + "164828.845.csv": ("M.099", "snapshot_end", "Snapshot END 2026-08-29 11:18:26.768Z txn 421072"),
}

DIAG = {
 Q + " (28).csv": ("H.001", "je_amount_reconciliation", "Source amount vs ledger net by source_table"),
 Q + " (29).csv": ("H.002", "je_source_counts", "Live source rows vs JE forward/reversal/distinct"),
 Q + " (30).csv": ("H.003", "je_stub_pollution", "Empty/zero JE by source_table"),
 Q + " (31).csv": ("H.004", "je_by_source_dates", "JE entry_date + posted_at range per source_table"),
 Q + " (32).csv": ("H.005", "je_reversal_summary", "14236 entries, 347 reversals (2.44 pct)"),
 Q + " (33).csv": ("H.006", "ar_definition_conflict", "v_outstanding_receivables vs v_tenant_current_dues"),
 Q + " (34).csv": ("H.007", "trial_balance_reversal_effect", "57 accounts: TB excl vs incl reversals"),
 Q + " (35).csv": ("H.008", "bed_apartment_status_matrix", "Live/Not-Active bed x apartment"),
 Q + " (36).csv": ("H.009", "entity_status_counts", "property/apartment/bed status counts"),
 Q + " (37).csv": ("H.010", "v_occupancy_snapshot_dup", "v_occupancy result - DUPLICATE of F.005"),
 Q + " (38).csv": ("H.011", "unbucketed_on_notice_beds", "THE 7 On-Notice-only beds (occupied=F booked=F on_notice=T)"),
 Q + " (39).csv": ("H.012", "occupancy_defs_ABC", "3 occupancy definitions A/B/C"),
 Q + " (40).csv": ("H.013", "allotment_status_rollup", "168 Staying / 7 On-Notice / 7 beds held / 0 both"),
 Q + " (41).csv": ("H.014", "staying_status_profile", "5 staying_status buckets with date ranges"),
 Q + " (42).csv": ("H.015", "v_active_tenants_snapshot_dup", "v_active_tenants - DUPLICATE of F.022"),
 Q + " (43).csv": ("H.016", "coa_accounts_flat", "57 chart-of-accounts rows with parent names"),
 Q + " (44).csv": ("H.017", "pnl_bucket_gap", "57 months: total_expenses vs sum_of_buckets vs unbucketed"),
 Q + " (45).csv": ("H.018", "resolutions_per_ticket", "462 tickets x1, 2 tickets x2 resolutions"),
 Q + " (46).csv": ("H.019", "maintenance_view_vs_actual", "view 1613 vs actual 1611 tickets"),
 Q + " (47).csv": ("H.020", "receipt_allocations_empty", "0 allocation rows vs 5758 live receipts"),
 Q + " (48).csv": ("H.020b", "receipt_allocations_empty_rerun", "EXACT DUPLICATE of H.020"),
 Q + " (49).csv": ("H.021", "journal_line_allotment_orphans", "14407 lines with allotment, 0 orphans"),
 Q + " (50).csv": ("H.022", "journal_lines_by_party_kind", "4 party_kind buckets debit/credit/net"),
 Q + " (51).csv": ("H.023", "party_kind_by_account", "22 party_kind x account rows"),
 Q + " (52).csv": ("H.024", "categorical_key_frequencies", "33 discriminator value counts"),
 Q + " (53).csv": ("H.025", "je_source_orphan_check", "3 source refs, 0 orphans"),
 Q + " (54).csv": ("H.026", "tenant_transactions_taxonomy", "17 ledger_type/direction/category combos"),
 Q + " (55).csv": ("H.027", "tenant_transactions_sample", "1 sample row"),
 Q + " (56).csv": ("H.028", "tenant_balance_4way_sample", "200 allotments x 4 competing balance definitions"),
 Q + " (57).csv": ("H.029", "owner_rent_missing_profit_dup", "46 months - DUPLICATE of F.028"),
 Q + " (58).csv": ("H.030", "pnl_owner_rent_vs_payments", "54 months: pnl_owner_rent vs owner_payments"),
 Q + " (59).csv": ("H.031", "live_equivalents_rowcounts", "15 legacy vs live table row counts"),
 Q + " (60).csv": ("H.032", "diagnostic_view_rowcounts", "8 diagnostic views + row counts"),
 Q + " (61).csv": ("H.033", "source_vs_ledger_diff_summary", "3 kinds: invoices/receipts/deposit_settlements"),
 Q + " (62).csv": ("H.034", "categorical_frequencies_full", "230 col/value/row frequency rows"),
 Q + " (63).csv": ("H.035", "invoice_type_status_matrix", "13 invoice_type x status x reference_type"),
 Q + " (64).csv": ("H.036", "lifecycle_events_sample500", "LIMIT-500 sample of v_tenant_lifecycle_events (full=2204)"),
 Q + " (65).csv": ("H.037", "market_schema_rowcounts", "7 of 17 market tables"),
 Q + " (66).csv": ("H.038", "trace_journal_lines_200", "ROW TRACE 200 journal lines with account+party"),
 Q + " (67).csv": ("H.039", "trace_tenant_transactions_200", "ROW TRACE 200 tenant_transactions"),
 Q + " (68).csv": ("H.040", "trace_invoices_drift_200", "ROW TRACE 200 invoices with drift column"),
 Q + " (69).csv": ("H.041", "trace_receipts_200", "ROW TRACE 200 receipts"),
 T + "163922.895.csv": ("H.001b", "je_amount_reconciliation_rerun", "EXACT DUPLICATE of H.001"),
 T + "163930.103.csv": ("H.002b", "je_source_counts_rerun", "EXACT DUPLICATE of H.002"),
 T + "163939.871.csv": ("H.003b", "je_stub_pollution_rerun", "Re-run of H.003 - compare row order/content"),
 T + "163948.943.csv": ("H.042", "je_intentional_skips", "20 deliberately-unposted source rows"),
 T + "163956.045.csv": ("H.043", "invoice_drift_rows", "2227 invoices with amount_paid/balance drift"),
 T + "164004.026.csv": ("H.044", "allotment_balance_drift_rows", "713 allotments stored vs computed balance"),
 T + "164012.559.csv": ("H.045", "deposit_phantom_rows", "32 phantom deposit rows"),
 T + "164021.735.csv": ("H.046", "deposit_ledger_anomalies", "22 deposit ledger anomalies"),
 T + "164040.168.csv": ("H.047", "exit_recon_worklist_dup", "EXACT DUPLICATE of F.027"),
 T + "164413.527.csv": ("H.048", "receipt_amount_vs_ledger_rows", "CONFLICT A: 11 receipts source vs ledger amount"),
 T + "164423.840.csv": ("H.049", "invoice_amount_vs_ledger_rows", "CONFLICT B: 120 invoices source vs ledger amount"),
 T + "164432.127.csv": ("H.050", "settlement_amount_vs_ledger_rows", "CONFLICT C: 43 settlements source vs ledger"),
 T + "164446.333.csv": ("H.051", "je_missing_deleted_sources", "CONFLICT E: 3 source_tables missing/soft-deleted source"),
 T + "164500.151.csv": ("H.052", "tenant_balance_4way_full", "CONFLICT G: 1213 allotments x 4 balance definitions"),
 T + "164507.566.csv": ("H.053", "bed_status_flags_23", "23 beds with occupied/booked/on_notice flags"),
 T + "164515.342.csv": ("H.054", "pnl_bucket_gap_dup", "EXACT DUPLICATE of H.017"),
 T + "164527.072.csv": ("H.055", "duplicate_invoices", "322 allotment/month/type duplicate invoice groups"),
 T + "164534.496.csv": ("H.056", "overlapping_allotments", "187 bed allotment overlap pairs"),
 T + "164541.966.csv": ("H.057", "period_value_coverage", "223 tbl/period/rows coverage rows"),
 T + "164750.925.csv": ("H.058", "maintenance_cost_linkage", "resolutions vs linked expenses vs closure cost"),
 Q + "..csv": ("H.012a", "occupancy_def_A", "A: v_occupancy Live bed+apt Staying only = 168/195"),
 "..csv": ("H.012b", "occupancy_def_B", "B: Live bed+apt Staying+On-Notice = 175/195"),
 Q + " (2)..csv": ("H.012c", "occupancy_def_C", "C: ALL beds Staying+On-Notice = 175/203"),
 Q + " (3)..csv": ("H.012d", "occupancy_def_D", "D: get_universal_metrics beds.status=Live Staying = 168/195"),
 Q + " (4)..csv": ("H.012e", "occupancy_def_E", "E: get_bed_occupancy_timeline Staying+On-Notice+Exited = 194/203"),
}

FN_BUNDLE = {
 T + "163440.513.csv": ("FN.000", "functions__business_logic", "25 business-logic function bodies, bundled"),
 T + "163450.107.csv": ("FN.999", "functions__remaining_inventory", "458 remaining routines, signature only"),
 T + "163515.048.csv": ("FN.TRG", "routines__trigger_wiring", "55 triggers: table, timing, events, function"),
}

FKEYS = {
 "v_pnl": "F.001", "v_pnl_by_category": "F.002", "v_revenue_by_period": "F.003",
 "v_expenses_by_period": "F.004", "v_occupancy": "F.005", "v_outstanding_receivables": "F.006",
 "v_tenant_current_dues": "F.007", "v_tenant_aging": "F.008", "v_invoice_settlement_status": "F.009",
 "v_advance_balances": "F.010", "v_org_cash_balance": "F.011", "v_trial_balance": "F.012",
 "v_trial_balance_detailed": "F.013", "v_account_rollup": "F.014", "v_maintenance_metrics": "F.015",
 "v_maintenance_by_issue_type": "F.016", "v_tenant_lifecycle_events": "F.017", "v_tenant_ledger": "F.018",
 "v_expense_composition": "F.019", "v_bed_expense_breakdown": "F.020", "v_account_balances": "F.021",
 "v_active_tenants": "F.022", "v_property_expense_share": "F.023", "v_asset_payment_status": "F.024",
 "maintenance_item_stock_summary": "F.025", "v_exit_reconciliation_worklist": "F.027",
 "v_diag_owner_rent_missing_from_profit": "F.028",
}
# F.026 = the second (byte-identical) stock-summary export at T161931.323
FBLOCK = set()
for t in ["160932.742", "160940.022", "160954.415", "161003.367", "161032.517", "161039.681",
          "161047.115", "161117.994", "161238.083", "161252.248", "161647.203", "161654.413",
          "161702.525", "161710.077", "161718.540", "161727.389", "161735.393", "161747.771",
          "161758.517", "161805.767", "161847.056", "161856.747", "161907.668", "161916.607",
          "161924.363", "161931.323", "161939.621", "161952.237"]:
    FBLOCK.add(T + t + ".csv")


OVERRIDE = {
 Q + " (72).csv": ("T.ai_logs", "public.ai_logs", "base table; prompt_excerpt/response_excerpt EXCLUDED (PII); +1 row vs M.006 (live write)"),
 Q + " (85).csv": ("T.bot_conversations", "public.bot_conversations", "AGGREGATE ONLY (1 summary row); transcript/phone EXCLUDED (PII). Row-level NOT exported"),
 Q + " (98).csv": ("T.enquiries", "public.enquiries", "base table; name/phone/raw_payload EXCLUDED, phone_hash derived"),
 T + "154246.392.csv": ("T.journal_lines", "public.journal_lines", "base table DENORMALISED: +6 cols joined from journal_entries (entry_date, period, posted_at, source_table, source_id, is_reversal_of)"),
 T + "154354.295.csv": ("T.maintenance_tickets", "public.maintenance_tickets", "base table; photo_urls/tenant_name/tenant_phone EXCLUDED; +1 row vs M.006 (live write)"),
 T + "154740.262.csv": ("T.profiles", "public.profiles", "base table; avatar_url/email/full_name/phone EXCLUDED; +1 row vs M.006 (live write)"),
 T + "155356.509.csv": ("T.tenants", "public.tenants", "base table; 27 PII cols EXCLUDED, phone_hash derived"),
 T + "155441.459.csv": ("T.ticket_logs", "public.ticket_logs", "base table; notes EXCLUDED; +1 row vs M.006 (live write)"),
 T + "155612.010.csv": ("T.user_roles", "public.user_roles", "base table, full column set; +1 row vs M.006 (live write)"),
}

rows = []
for r in fp:
    f = r['file']
    h = set(r['cols'])
    n = r['rows']
    if f in OVERRIDE:
        k, ln, note = OVERRIDE[f]; cls = 'base_table'
    elif f in META:
        k, ln, note = META[f]; cls = 'metadata'
    elif f in DIAG:
        k, ln, note = DIAG[f]; cls = 'diagnostic'
    elif f in FN_BUNDLE:
        k, ln, note = FN_BUNDLE[f]; cls = 'functions'
    elif set(r['cols']) == {'schema_name', 'routine_name', 'arguments', 'return_type', 'definition'} and n == 1:
        with open(f, encoding='utf-8-sig', newline='') as fh:
            d = next(csv.DictReader(fh))
        k = 'FN.' + d['routine_name']; ln = 'fn__' + d['routine_name']
        note = 'Full CREATE definition (' + str(len(d['definition'])) + ' chars)'; cls = 'functions'
    else:
        tc = [t for t, s in tabsig.items() if h and h <= s and rc.get(t) == n]
        vc = [v for v, s in vcols.items() if h and h <= s and len(h) >= max(2, 0.5 * len(s))]
        vc = [v for v in vc if not v.startswith('public.v_export_')]
        if len(tc) == 1:
            k = 'T.' + tc[0].split('.')[1]; ln = tc[0]; note = 'base table export'; cls = 'base_table'
        elif vc:
            vc = sorted(vc, key=lambda z: 0 if z.endswith('stock_summary') else 1)
            nm = vc[0].split('.')[1]
            if f == T + "161931.323.csv":
                k = 'F.026'; note = 'EXACT DUPLICATE of F.025'
            elif f in FBLOCK:
                k = FKEYS.get(nm, 'F.???'); note = 'business view export'
            else:
                k = 'V.' + nm; note = 'view export'
            ln = vc[0]
            if len(vc) > 1:
                note += ' [ambiguous: ' + '/'.join(vc) + ']'
            cls = 'view'
        else:
            k = '?'; ln = 'UNRESOLVED'; note = ''; cls = 'unknown'
    rows.append({'key': k, 'logical_name': ln, 'class': cls, 'rows': n,
                 'cols': r['ncols'], 'bytes': r['bytes'], 'file': f, 'note': note})

outp = os.path.join(base, 'evidence', 'file_manifest.csv')
os.makedirs(os.path.dirname(outp), exist_ok=True)
with open(outp, 'w', newline='', encoding='utf-8') as fh:
    w = csv.DictWriter(fh, fieldnames=['key', 'logical_name', 'class', 'rows', 'cols', 'bytes', 'file', 'note'])
    w.writeheader()
    for x in sorted(rows, key=lambda z: (z['class'], z['key'])):
        w.writerow(x)
print(collections.Counter(x['class'] for x in rows))
print("total files:", len(rows))
print("UNRESOLVED:", [(x['file'][:45], x['rows'], x['cols']) for x in rows if x['class'] == 'unknown'])
print("F-keys assigned:", sorted(x['key'] for x in rows if x['key'].startswith('F.')))
