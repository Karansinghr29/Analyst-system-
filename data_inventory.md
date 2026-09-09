# A. data_inventory.md

Evidence-derived inventory of every object in the exported package.

**Source of truth for this document**

| Fact | Evidence file (manifest key) |
|---|---|
| object type, size, dropped columns | M.003 `object_inventory` |
| exact row counts (counted 2026-08-29 09:02:53Z) | M.006 `row_counts_exact` |
| column names/types | M.004 `column_inventory` |
| date coverage | M.025 `temporal_profile` |
| organization_id presence | M.007 `organization_grain` |
| foreign keys | M.009 `foreign_keys` |
| sensitivity / PII exclusions | M.027 `sensitive_columns` |
| view SQL + columns | M.016 / M.017 |
| opaque filename -> object mapping | `evidence/file_manifest.csv` |

`exported_rows` is counted directly from the CSV. `counted_rows` is M.006. A non-zero delta is recorded, never silently reconciled.

---

## A.1 Public base tables (131)

### `accounting_migration_log`

- **object type:** table  |  **size:** 80 kB
- **counted rows (M.006):** 30
- **exported rows:** 30  (matches)
- **export file:** manifest key `T.accounting_migration_log`
- **columns (7):** id, phase, severity, message, payload, sql_state, created_at
- **organization_id:** absent
- **foreign keys:** none declared
- **date coverage:** created_at 2026-04-25..2026-05-09 (2 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `accounting_periods`

- **object type:** table  |  **size:** 16 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (6):** organization_id, period, status, closed_at, closed_by, notes
- **organization_id:** present; distinct_orgs=0, null_org_rows=0
- **foreign keys (2):** closed_by -> users.id [NO ACTION]; organization_id -> organizations.id [CASCADE]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `ai_actions`

- **object type:** table  |  **size:** 48 kB
- **counted rows (M.006):** 7
- **exported rows:** 7  (matches)
- **export file:** manifest key `T.ai_actions`
- **columns (10):** id, user_id, organization_id, session_id, action, payload, result, status, error_message, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (3):** organization_id -> organizations.id [CASCADE]; session_id -> ai_sessions.id [SET NULL]; user_id -> users.id [CASCADE]
- **date coverage:** created_at 2026-04-18..2026-04-20 (1 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `ai_logs`

- **object type:** table  |  **size:** 8008 kB
- **counted rows (M.006):** 6765
- **exported rows:** 6766  **(delta +1 vs M.006)**
- **export file:** manifest key `T.ai_logs`
- **export note:** base table; prompt_excerpt/response_excerpt EXCLUDED (PII); +1 row vs M.006 (live write)
- **columns (11):** id, request_type, model, latency_ms, success, error_message, metadata, prompt_excerpt, response_excerpt, redaction_level, created_at
- **organization_id:** absent
- **foreign keys:** none declared
- **date coverage:** created_at 2026-04-19..2026-08-29 (5 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `ai_sessions`

- **object type:** table  |  **size:** 96 kB
- **counted rows (M.006):** 14
- **exported rows:** 14  (matches)
- **export file:** manifest key `T.ai_sessions`
- **columns (12):** id, user_id, organization_id, status, pending_action, collected_data, missing_fields, last_plan, conversation, disambiguation_candidates, created_at, updated_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** organization_id -> organizations.id [CASCADE]; user_id -> users.id [CASCADE]
- **date coverage:** created_at 2026-04-18..2026-04-28 (1 mo); updated_at 2026-04-18..2026-04-28 (1 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `announcements`

- **object type:** table  |  **size:** 32 kB
- **counted rows (M.006):** 1
- **exported rows:** 1  (matches)
- **export file:** manifest key `T.announcements`
- **columns (11):** id, organization_id, title, content, priority, is_published, published_at, created_by, created_at, updated_at, image_url
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** created_by -> users.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]
- **date coverage:** created_at 2026-08-05..2026-08-05 (1 mo); updated_at 2026-08-05..2026-08-05 (1 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `apartments`

- **object type:** table  |  **size:** 104 kB
- **counted rows (M.006):** 43
- **exported rows:** 43  (matches)
- **export file:** manifest key `T.apartments`
- **columns (29):** id, organization_id, property_id, apartment_code, floor_number, status, created_at, apartment_type, size_sqft, owner_id, gender_allowed, eb_meter_number, start_date, end_date, signing_date, property_tax_id, property_tax_amount, property_tax_frequency, water_tax_id, water_tax_amount, water_tax_frequency, ownership_doc_url, eb_card_number, eb_consumer_number, eb_connection_type, eb_sanctioned_load, eb_card_photo_url, star_rating, star_rating_override
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (3):** organization_id -> organizations.id [NO ACTION]; owner_id -> owners.id [NO ACTION]; property_id -> properties.id [CASCADE]
- **date coverage:** created_at 2026-03-16..2026-07-28 (3 mo); end_date 2024-08-31..2032-03-31 (11 mo); signing_date 2026-08-01..2026-08-01 (1 mo); start_date 1899-12-30..2026-08-01 (12 mo)
- **sensitivity:** EXCLUDED: eb_card_photo_url
- **analytics suitability:** **Yes - primary occupancy/tenancy evidence.**

### `asset_allocations`

- **object type:** table  |  **size:** 544 kB
- **counted rows (M.006):** 1822
- **exported rows:** 1822  (matches)
- **export file:** manifest key `T.asset_allocations`
- **columns (10):** id, organization_id, asset_id, allocation_type, property_id, apartment_id, bed_id, allocated_date, allocated_by, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (6):** allocated_by -> users.id [NO ACTION]; apartment_id -> apartments.id [NO ACTION]; asset_id -> assets.id [CASCADE]; bed_id -> beds.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]; property_id -> properties.id [NO ACTION]
- **date coverage:** allocated_date 2023-03-30..2026-04-10 (21 mo); created_at 2026-04-10..2026-04-10 (1 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `asset_brands`

- **object type:** table  |  **size:** 48 kB
- **counted rows (M.006):** 50
- **exported rows:** 50  (matches)
- **export file:** manifest key `T.asset_brands`
- **columns (4):** id, name, organization_id, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (1):** organization_id -> organizations.id [NO ACTION]
- **date coverage:** created_at 2026-03-18..2026-04-10 (2 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `asset_categories`

- **object type:** table  |  **size:** 32 kB
- **counted rows (M.006):** 11
- **exported rows:** 11  (matches)
- **export file:** manifest key `T.asset_categories`
- **columns (4):** id, organization_id, name, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (1):** organization_id -> organizations.id [NO ACTION]
- **date coverage:** created_at 2026-03-16..2026-04-22 (2 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `asset_depreciation`

- **object type:** table  |  **size:** 16 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (9):** id, asset_id, purchase_price, residual_value, useful_life_years, current_book_value, yearly_depreciation, last_calculated, organization_id
- **organization_id:** present; distinct_orgs=0, null_org_rows=0
- **foreign keys (1):** asset_id -> assets.id [CASCADE]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `asset_maintenance_logs`

- **object type:** table  |  **size:** 16 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (10):** id, organization_id, asset_id, maintenance_type, issue, repair_cost, vendor, maintenance_date, next_service_due, created_at
- **organization_id:** present; distinct_orgs=0, null_org_rows=0
- **foreign keys (2):** asset_id -> assets.id [CASCADE]; organization_id -> organizations.id [NO ACTION]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `asset_movements`

- **object type:** table  |  **size:** 16 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (9):** id, organization_id, asset_id, from_location, to_location, moved_by, move_date, reason, created_at
- **organization_id:** present; distinct_orgs=0, null_org_rows=0
- **foreign keys (3):** asset_id -> assets.id [CASCADE]; moved_by -> users.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `asset_payments`

- **object type:** table  |  **size:** 56 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (13):** id, organization_id, asset_id, vendor_id, payment_date, amount, payment_mode, bank_account_id, reference_number, payment_proof_url, notes, created_at, created_by
- **organization_id:** present; distinct_orgs=0, null_org_rows=0
- **foreign keys (4):** asset_id -> assets.id [RESTRICT]; bank_account_id -> organization_bank_accounts.id [SET NULL]; organization_id -> organizations.id [CASCADE]; vendor_id -> vendors.id [SET NULL]
- **date coverage:** no dated column profiled
- **sensitivity:** EXCLUDED: payment_proof_url | HASHED: bank_account_id
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `asset_types`

- **object type:** table  |  **size:** 72 kB
- **counted rows (M.006):** 34
- **exported rows:** 34  (matches)
- **export file:** manifest key `T.asset_types`
- **columns (10):** id, organization_id, category_id, name, expected_life_months, depreciation_method, depreciation_years, maintenance_cycle_months, replacement_cost_estimate, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** category_id -> asset_categories.id [CASCADE]; organization_id -> organizations.id [NO ACTION]
- **date coverage:** created_at 2026-04-08..2026-04-22 (1 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `assets`

- **object type:** table  |  **size:** 848 kB
- **counted rows (M.006):** 1700
- **exported rows:** 1700  (matches)
- **export file:** manifest key `T.assets`
- **columns (29):** id, organization_id, asset_type_id, asset_code, qr_code, serial_number, brand, model, purchase_date, purchase_price, supplier_id, warranty_months, warranty_expiry, condition, status, notes, created_at, invoice_number, invoice_date, invoice_url, vendor_name_manual, capacity_value, capacity_unit, product_photo_url, apartment_id, bed_id, is_bill_missing, data_source, migration_notes
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (4):** apartment_id -> apartments.id [NO ACTION]; asset_type_id -> asset_types.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]; supplier_id -> vendors.id [NO ACTION]
- **date coverage:** created_at 2026-04-10..2026-04-10 (1 mo); invoice_date 2023-03-30..2026-03-23 (25 mo); purchase_date 2023-03-30..2026-03-23 (25 mo); warranty_expiry 2026-07-31..2026-07-31 (1 mo)
- **sensitivity:** EXCLUDED: product_photo_url
- **analytics suitability:** Supporting / operational.

### `attendance_logs`

- **object type:** table  |  **size:** 40 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (24):** id, employee_id, company_id, date, check_in_time, check_out_time, status, hours_worked, overtime_hours, late_minutes, bonus, total_deduction_percent, notes, edit_reason, edited_by, source, marked_by, check_in_image_account, check_out_image_account, check_in_device_id, check_out_device_id, extended_checkout_time, shift_id, created_at
- **organization_id:** absent
- **foreign keys (3):** company_id -> companies.id [SET NULL]; edited_by -> users.id [NO ACTION]; employee_id -> employees.id [CASCADE]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `attendance_sync`

- **object type:** table  |  **size:** 96 kB
- **counted rows (M.006):** 50
- **exported rows:** 50  (matches)
- **export file:** manifest key `T.attendance_sync`
- **columns (13):** id, record_id, employee_name, employee_email, department, date, check_in_time, check_out_time, status, hours_worked, notes, synced_at, created_at
- **organization_id:** absent
- **foreign keys:** none declared
- **date coverage:** created_at 2026-05-23..2026-08-21 (3 mo); date 2026-03-11..2026-05-23 (3 mo); synced_at 2026-05-23..2026-08-22 (3 mo)
- **sensitivity:** HASHED: employee_email
- **analytics suitability:** Supporting / operational.

### `audit_logs`

- **object type:** table  |  **size:** 1984 kB
- **counted rows (M.006):** 3119
- **exported rows:** 3119  (matches)
- **export file:** manifest key `T.audit_logs`
- **columns (10):** id, organization_id, table_name, record_id, action, changes, performed_by, performed_at, old_value, new_value
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (1):** organization_id -> organizations.id [NO ACTION]
- **date coverage:** performed_at 2026-03-16..2026-08-28 (6 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `bed_rates`

- **object type:** table  |  **size:** 72 kB
- **counted rows (M.006):** 24
- **exported rows:** 24  (matches)
- **export file:** manifest key `T.bed_rates`
- **columns (9):** id, organization_id, property_id, bed_type, toilet_type, monthly_rate, from_date, to_date, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** organization_id -> organizations.id [NO ACTION]; property_id -> properties.id [NO ACTION]
- **date coverage:** created_at 2025-04-29..2025-04-29 (1 mo); from_date 2022-01-01..2025-05-01 (4 mo); to_date 2024-01-31..2026-12-31 (4 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **Yes - primary occupancy/tenancy evidence.**

### `bed_status_history`

- **object type:** table  |  **size:** 16 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (8):** id, bed_id, status, from_date, to_date, notes, organization_id, created_at
- **organization_id:** present; distinct_orgs=0, null_org_rows=0
- **foreign keys (2):** bed_id -> beds.id [CASCADE]; organization_id -> organizations.id [NO ACTION]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `bed_type_config`

- **object type:** table  |  **size:** 24 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (5):** id, name, organization_id, sort_order, created_at
- **organization_id:** present; distinct_orgs=0, null_org_rows=0
- **foreign keys (1):** organization_id -> organizations.id [NO ACTION]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `beds`

- **object type:** table  |  **size:** 224 kB
- **counted rows (M.006):** 203
- **exported rows:** 203  (matches)
- **export file:** manifest key `T.beds`
- **columns (9):** id, organization_id, apartment_id, bed_code, bed_type, toilet_type, status, created_at, bed_lifecycle_status
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** apartment_id -> apartments.id [CASCADE]; organization_id -> organizations.id [NO ACTION]
- **date coverage:** created_at 2026-03-16..2026-07-29 (4 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **Yes - primary occupancy/tenancy evidence.**

### `bot_conversations`

- **object type:** table  |  **size:** 96 kB
- **counted rows (M.006):** 9
- **exported rows:** 1  **(delta -8 vs M.006)**
- **export file:** manifest key `T.bot_conversations`
- **export note:** AGGREGATE ONLY (1 summary row); transcript/phone EXCLUDED (PII). Row-level NOT exported
- **columns (3):** phone, transcript, updated_at
- **organization_id:** absent
- **foreign keys:** none declared
- **date coverage:** updated_at 2026-07-08..2026-07-09 (1 mo)
- **sensitivity:** HASHED: phone
- **analytics suitability:** **No** - only an aggregate summary row exported; row level withheld as PII.

### `coa_accounts`

- **object type:** table  |  **size:** 80 kB
- **counted rows (M.006):** 57
- **exported rows:** 57  (matches)
- **export file:** manifest key `T.coa_accounts`
- **columns (13):** id, organization_id, code, name, account_type, normal_balance, parent_id, is_active, requires_party, requires_allotment, party_kind, description, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** organization_id -> organizations.id [CASCADE]; parent_id -> coa_accounts.id [RESTRICT]
- **date coverage:** created_at 2026-04-25..2026-05-09 (2 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **Yes - primary ledger evidence.** Reversal and soft-delete handling mandatory.

### `companies`

- **object type:** table  |  **size:** 24 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (11):** id, name, address, gst_number, late_threshold_minutes, overtime_threshold_hours, weekly_off_day, bonus, status, shared_account_only_departments, created_at
- **organization_id:** absent
- **foreign keys:** none declared
- **date coverage:** no dated column profiled
- **sensitivity:** HASHED: gst_number
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `cost_estimate_approvers`

- **object type:** table  |  **size:** 32 kB
- **counted rows (M.006):** 1
- **exported rows:** 1  (matches)
- **export file:** manifest key `T.cost_estimate_approvers`
- **columns (7):** id, organization_id, approver_user_id, scope_type, property_id, issue_type_id, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (3):** issue_type_id -> issue_types.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]; property_id -> properties.id [NO ACTION]
- **date coverage:** created_at 2026-03-27..2026-03-27 (1 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `departments`

- **object type:** table  |  **size:** 24 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (4):** id, name, company_id, created_at
- **organization_id:** absent
- **foreign keys (1):** company_id -> companies.id [CASCADE]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `deposit_settlements`

- **object type:** table  |  **size:** 216 kB
- **counted rows (M.006):** 307
- **exported rows:** 307  (matches)
- **export file:** manifest key `T.deposit_settlements`
- **columns (17):** id, organization_id, tenant_id, allotment_id, deposit_amount, pending_rent, pending_eb, pending_late_fees, damages, other_deductions, total_deductions, refund_amount, settlement_date, status, notes, created_at, is_deleted
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (3):** allotment_id -> tenant_allotments.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]; tenant_id -> tenants.id [NO ACTION]
- **date coverage:** created_at 2026-04-06..2026-08-28 (5 mo); settlement_date 2023-04-03..2026-09-20 (35 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **Yes - primary financial evidence.**

### `diagnostic_sessions`

- **object type:** table  |  **size:** 1136 kB
- **counted rows (M.006):** 479
- **exported rows:** 479  (matches)
- **export file:** manifest key `T.diagnostic_sessions`
- **columns (11):** id, ticket_id, organization_id, performed_by, issue_type_id, questions_answers, ai_diagnosis, employee_override, status, created_at, completed_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (3):** issue_type_id -> issue_types.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]; ticket_id -> maintenance_tickets.id [CASCADE]
- **date coverage:** completed_at 2026-04-09..2026-08-24 (5 mo); created_at 2026-04-09..2026-08-24 (5 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `eb_monitoring_readings`

- **object type:** table  |  **size:** 136 kB
- **counted rows (M.006):** 35
- **exported rows:** 35  (matches)
- **export file:** manifest key `T.eb_monitoring_readings`
- **columns (13):** id, organization_id, property_id, apartment_id, reading_date, start_reading, start_month, current_reading, units_consumed, eb_amount, is_danger, meter_photo_url, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys:** none declared
- **date coverage:** created_at 2026-06-28..2026-06-28 (1 mo); reading_date 2026-08-18..2026-08-18 (1 mo)
- **sensitivity:** EXCLUDED: meter_photo_url
- **analytics suitability:** Supporting / operational.

### `eb_payments`

- **object type:** table  |  **size:** 160 kB
- **counted rows (M.006):** 70
- **exported rows:** 70  (matches)
- **export file:** manifest key `T.eb_payments`
- **columns (16):** id, organization_id, property_id, bill_date, bill_amount, payment_date, payment_mode, reference_number, billing_period_start, billing_period_end, notes, is_locked, locked_by, created_at, apartment_id, bank_account_id
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (4):** apartment_id -> apartments.id [NO ACTION]; bank_account_id -> organization_bank_accounts.id [SET NULL]; organization_id -> organizations.id [NO ACTION]; property_id -> properties.id [NO ACTION]
- **date coverage:** bill_date 2026-04-29..2026-06-27 (2 mo); billing_period_end 2026-04-12..2026-06-16 (2 mo); billing_period_start 2026-02-07..2026-04-12 (2 mo); created_at 2026-06-12..2026-07-02 (2 mo); payment_date 2026-05-05..2026-07-02 (2 mo)
- **sensitivity:** HASHED: bank_account_id
- **analytics suitability:** **Yes - primary financial evidence.**

### `eb_rates`

- **object type:** table  |  **size:** 40 kB
- **counted rows (M.006):** 2
- **exported rows:** 2  (matches)
- **export file:** manifest key `T.eb_rates`
- **columns (7):** id, organization_id, property_id, unit_cost, from_date, to_date, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** organization_id -> organizations.id [NO ACTION]; property_id -> properties.id [NO ACTION]
- **date coverage:** created_at 2026-03-17..2026-03-18 (1 mo); from_date 2021-01-01..2024-07-01 (2 mo); to_date 2024-06-30..2024-06-30 (1 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `eb_tenant_shares`

- **object type:** table  |  **size:** 864 kB
- **counted rows (M.006):** 801
- **exported rows:** 801  (matches)
- **export file:** manifest key `T.eb_tenant_shares`
- **columns (14):** id, invoice_id, apartment_id, billing_month, total_apartment_bill, total_tenant_days, per_day_rate, tenant_stay_days, tenant_eb_charge, total_units, unit_cost, created_at, organization_id, tenant_id
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (3):** apartment_id -> apartments.id [NO ACTION]; invoice_id -> invoices.id [CASCADE]; tenant_id -> tenants.id [NO ACTION]
- **date coverage:** created_at 2026-04-07..2026-08-08 (5 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **Yes - primary financial evidence.**

### `electricity_readings`

- **object type:** table  |  **size:** 768 kB
- **counted rows (M.006):** 1411
- **exported rows:** 1411  (matches)
- **export file:** manifest key `T.electricity_readings`
- **columns (13):** id, organization_id, property_id, apartment_id, reading_start, reading_end, units_consumed, unit_cost, billing_month, created_at, meter_photo_url, is_locked, locked_by
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (3):** apartment_id -> apartments.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]; property_id -> properties.id [NO ACTION]
- **date coverage:** created_at 2026-03-20..2026-07-31 (5 mo)
- **sensitivity:** EXCLUDED: meter_photo_url
- **analytics suitability:** **Yes - primary financial evidence.**

### `electricity_shares`

- **object type:** table  |  **size:** 8192 bytes
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (6):** id, electricity_reading_id, tenant_id, units_allocated, cost_share, created_at
- **organization_id:** absent
- **foreign keys (2):** electricity_reading_id -> electricity_readings.id [CASCADE]; tenant_id -> tenants.id [NO ACTION]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `email_templates`

- **object type:** table  |  **size:** 200 kB
- **counted rows (M.006):** 4
- **exported rows:** 4  (matches)
- **export file:** manifest key `T.email_templates`
- **columns (10):** id, organization_id, email_type, subject_template, html_template, design_json, is_default, version, created_at, updated_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=3 **<- NULL org rows present**
- **foreign keys (1):** organization_id -> organizations.id [CASCADE]
- **date coverage:** created_at 2026-04-21..2026-04-21 (1 mo); updated_at 2026-04-21..2026-04-22 (1 mo)
- **sensitivity:** HASHED: email_type
- **analytics suitability:** Supporting / operational.

### `employee_specialties`

- **object type:** table  |  **size:** 32 kB
- **counted rows (M.006):** 10
- **exported rows:** 10  (matches)
- **export file:** manifest key `T.employee_specialties`
- **columns (4):** id, user_id, specialty, created_at
- **organization_id:** absent
- **foreign keys (1):** user_id -> users.id [CASCADE]
- **date coverage:** created_at 2026-03-30..2026-08-12 (3 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `employees`

- **object type:** table  |  **size:** 56 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (24):** id, employee_id, first_name, last_name, full_name, email, department, department_id, position, company_id, shift_id, salary_type, salary_rate, branch, bonus, status, face_registered, face_descriptor, bank_name, bank_account_number, bank_ifsc_code, aadhar_number, user_id, created_at
- **organization_id:** absent
- **foreign keys (3):** company_id -> companies.id [SET NULL]; department_id -> departments.id [NO ACTION]; user_id -> users.id [NO ACTION]
- **date coverage:** no dated column profiled
- **sensitivity:** EXCLUDED: face_descriptor | HASHED: aadhar_number, bank_account_number, bank_ifsc_code, email | kept-but-flagged: first_name, full_name, last_name
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `employees_sync`

- **object type:** table  |  **size:** 80 kB
- **counted rows (M.006):** 23
- **exported rows:** 23  (matches)
- **export file:** manifest key `T.employees_sync`
- **columns (19):** id, record_id, employee_code, first_name, last_name, email, department, position, company_name, shift_name, salary_type, salary_rate, bank_name, bank_account, ifsc_code, aadhar_number, status, synced_at, created_at
- **organization_id:** absent
- **foreign keys:** none declared
- **date coverage:** created_at 2026-05-09..2026-08-07 (3 mo); synced_at 2026-07-08..2026-08-29 (2 mo)
- **sensitivity:** HASHED: aadhar_number, bank_account, email, ifsc_code | kept-but-flagged: first_name, last_name
- **analytics suitability:** Supporting / operational.

### `enquiries`

- **object type:** table  |  **size:** 96 kB
- **counted rows (M.006):** 18
- **exported rows:** 18  (matches)
- **export file:** manifest key `T.enquiries`
- **export note:** base table; name/phone/raw_payload EXCLUDED, phone_hash derived
- **columns (15):** id, organization_id, phone, name, language, move_in_date, bed_type, gender, property_interest, budget, status, source, raw_payload, created_at, updated_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys:** none declared
- **date coverage:** created_at 2026-07-02..2026-07-09 (1 mo); move_in_date 2024-01-01..2024-01-01 (1 mo); updated_at 2026-07-02..2026-07-09 (1 mo)
- **sensitivity:** HASHED: phone
- **analytics suitability:** Supporting / operational.

### `exit_tasks`

- **object type:** table  |  **size:** 64 kB
- **counted rows (M.006):** 3
- **exported rows:** 3  (matches)
- **export file:** manifest key `T.exit_tasks`
- **columns (17):** id, organization_id, allotment_id, tenant_id, exit_date, assigned_to, assigned_at, status, checklist, refund_details, tenant_approval_sent, tenant_approved, tenant_approved_at, completed_by, completed_at, notes, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** allotment_id -> tenant_allotments.id [NO ACTION]; tenant_id -> tenants.id [NO ACTION]
- **date coverage:** assigned_at 2026-04-16..2026-08-10 (2 mo); created_at 2026-04-16..2026-08-10 (2 mo); exit_date 2026-04-16..2026-08-08 (2 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `expense_bed_allocations`

- **object type:** table  |  **size:** 264 kB
- **counted rows (M.006):** 448
- **exported rows:** 448  (matches)
- **export file:** manifest key `T.expense_bed_allocations`
- **columns (6):** id, expense_id, bed_id, organization_id, allocated_amount, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (3):** bed_id -> beds.id [NO ACTION]; expense_id -> expenses.id [CASCADE]; organization_id -> organizations.id [NO ACTION]
- **date coverage:** created_at 2026-04-11..2026-04-11 (1 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **Yes - primary financial evidence.**

### `expense_categories`

- **object type:** table  |  **size:** 80 kB
- **counted rows (M.006):** 9
- **exported rows:** 9  (matches)
- **export file:** manifest key `T.expense_categories`
- **columns (8):** id, organization_id, key, label, sort_order, is_active, created_at, gl_account_id
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** gl_account_id -> coa_accounts.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]
- **date coverage:** created_at 2026-04-11..2026-05-20 (2 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `expense_subcategories`

- **object type:** table  |  **size:** 80 kB
- **counted rows (M.006):** 10
- **exported rows:** 10  (matches)
- **export file:** manifest key `T.expense_subcategories`
- **columns (9):** id, organization_id, category_id, key, label, sort_order, is_active, created_at, gl_account_id
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (3):** category_id -> expense_categories.id [CASCADE]; gl_account_id -> coa_accounts.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]
- **date coverage:** created_at 2026-04-08..2026-04-08 (1 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `expenses`

- **object type:** table  |  **size:** 744 kB
- **counted rows (M.006):** 516
- **exported rows:** 516  (matches)
- **export file:** manifest key `T.expenses`
- **columns (21):** id, organization_id, property_id, apartment_id, bed_id, description, amount, expense_date, billing_month, receipt_url, created_at, data_source, related_asset_id, category_id, subcategory_id, vendor_id, asset_type_id, issue_type_id, ticket_resolution_id, bank_account_id, team_payment_id
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (13):** apartment_id -> apartments.id [NO ACTION]; asset_type_id -> asset_types.id [NO ACTION]; bank_account_id -> organization_bank_accounts.id [SET NULL]; bed_id -> beds.id [NO ACTION]; category_id -> expense_categories.id [NO ACTION]; issue_type_id -> issue_types.id [SET NULL]; organization_id -> organizations.id [NO ACTION]; property_id -> properties.id [NO ACTION]; related_asset_id -> assets.id [NO ACTION]; subcategory_id -> expense_subcategories.id [NO ACTION]; team_payment_id -> team_payments.id [CASCADE]; ticket_resolution_id -> ticket_resolutions.id [CASCADE] ...
- **date coverage:** created_at 2026-04-11..2026-08-24 (4 mo); expense_date 2023-03-11..2026-08-24 (35 mo)
- **sensitivity:** HASHED: bank_account_id
- **analytics suitability:** **Yes - primary financial evidence.**

### `export_entity_registry`

- **object type:** table  |  **size:** 32 kB
- **counted rows (M.006):** 17
- **exported rows:** 17  (matches)
- **export file:** manifest key `T.export_entity_registry`
- **columns (5):** entity_key, view_name, label, module, sort_order
- **organization_id:** absent
- **foreign keys:** none declared
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `financial_audit_log`

- **object type:** table  |  **size:** 8448 kB
- **counted rows (M.006):** 23132
- **exported rows:** 23132  (matches)
- **export file:** manifest key `T.financial_audit_log`
- **columns (12):** id, organization_id, journal_entry_id, operation, actor_user_id, source_table, source_id, period, total_debit, total_credit, metadata, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** actor_user_id -> users.id [NO ACTION]; journal_entry_id -> journal_entries.id [SET NULL]
- **date coverage:** created_at 2026-04-26..2026-08-29 (5 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **Yes - primary ledger evidence.** Reversal and soft-delete handling mandatory.

### `gst_monthly_workings`

- **object type:** table  |  **size:** 240 kB
- **counted rows (M.006):** 5
- **exported rows:** 5  (matches)
- **export file:** manifest key `T.gst_monthly_workings`
- **columns (10):** id, organization_id, month, year, generated_at, generated_by, tenant_json, summary_json, rcm_json, last_updated_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** generated_by -> profiles.id [SET NULL]; organization_id -> organizations.id [CASCADE]
- **date coverage:** generated_at 2026-04-17..2026-08-13 (5 mo); last_updated_at 2026-04-17..2026-08-13 (5 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `invoice_line_items`

- **object type:** table  |  **size:** 5056 kB
- **counted rows (M.006):** 5536
- **exported rows:** 5536  (matches)
- **export file:** manifest key `T.invoice_line_items`
- **columns (8):** id, invoice_id, line_type, description, amount, created_at, metadata, organization_id
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (1):** invoice_id -> invoices.id [CASCADE]
- **date coverage:** created_at 2026-03-28..2026-08-28 (6 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **Yes - primary financial evidence.**

### `invoice_pdf_configs`

- **object type:** table  |  **size:** 48 kB
- **counted rows (M.006):** 2
- **exported rows:** 2  (matches)
- **export file:** manifest key `T.invoice_pdf_configs`
- **columns (26):** id, organization_id, config_type, logo_url, accent_color, header_bg_color, pan_number, cin_number, tax_label, bank_name, account_number, ifsc_code, upi_id, qr_code_url, terms_and_conditions, footer_notes, signatory_name, signatory_title, number_prefix, created_at, updated_at, layout_style, body_text_color, muted_text_color, header_text_color, style_options
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (1):** organization_id -> organizations.id [CASCADE]
- **date coverage:** created_at 2026-05-13..2026-05-14 (1 mo); updated_at 2026-05-15..2026-06-02 (2 mo)
- **sensitivity:** HASHED: account_number, ifsc_code, pan_number, upi_id
- **analytics suitability:** Supporting / operational.

### `invoices`

- **object type:** table  |  **size:** 5592 kB
- **counted rows (M.006):** 5214
- **exported rows:** 5214  (matches)
- **export file:** manifest key `T.invoices`
- **columns (26):** id, organization_id, tenant_id, property_id, apartment_id, bed_id, invoice_number, invoice_date, due_date, rent_amount, electricity_amount, other_charges, total_amount, status, created_at, late_fee, locked, billing_month, allotment_id, estimated_eb, amount_paid, balance, is_deleted, invoice_type, reference_type, reference_id
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (6):** allotment_id -> tenant_allotments.id [SET NULL]; apartment_id -> apartments.id [NO ACTION]; bed_id -> beds.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]; property_id -> properties.id [NO ACTION]; tenant_id -> tenants.id [NO ACTION]
- **date coverage:** created_at 2026-03-28..2026-08-29 (6 mo); due_date 2023-02-09..2026-09-20 (44 mo); invoice_date 2023-02-05..2026-09-20 (44 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **Yes - primary financial evidence.**

### `issue_sub_types`

- **object type:** table  |  **size:** 64 kB
- **counted rows (M.006):** 51
- **exported rows:** 51  (matches)
- **export file:** manifest key `T.issue_sub_types`
- **columns (8):** id, issue_type_id, organization_id, name, icon, description, sort_order, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** issue_type_id -> issue_types.id [CASCADE]; organization_id -> organizations.id [CASCADE]
- **date coverage:** created_at 2026-03-18..2026-04-18 (2 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `issue_type_asset_types`

- **object type:** table  |  **size:** 72 kB
- **counted rows (M.006):** 33
- **exported rows:** 33  (matches)
- **export file:** manifest key `T.issue_type_asset_types`
- **columns (5):** id, organization_id, issue_type_id, asset_type_id, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (3):** asset_type_id -> asset_types.id [CASCADE]; issue_type_id -> issue_types.id [CASCADE]; organization_id -> organizations.id [CASCADE]
- **date coverage:** created_at 2026-04-18..2026-04-18 (1 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `issue_type_expense_mapping`

- **object type:** table  |  **size:** 56 kB
- **counted rows (M.006):** 14
- **exported rows:** 14  (matches)
- **export file:** manifest key `T.issue_type_expense_mapping`
- **columns (7):** id, organization_id, issue_type_id, expense_category_id, expense_subcategory_id, gl_account_id, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (5):** expense_category_id -> expense_categories.id [SET NULL]; expense_subcategory_id -> expense_subcategories.id [SET NULL]; gl_account_id -> coa_accounts.id [RESTRICT]; issue_type_id -> issue_types.id [CASCADE]; organization_id -> organizations.id [CASCADE]
- **date coverage:** created_at 2026-04-25..2026-04-25 (1 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `issue_types`

- **object type:** table  |  **size:** 32 kB
- **counted rows (M.006):** 14
- **exported rows:** 14  (matches)
- **export file:** manifest key `T.issue_types`
- **columns (7):** id, organization_id, name, icon, priority, sla_hours, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (1):** organization_id -> organizations.id [NO ACTION]
- **date coverage:** created_at 2026-03-16..2026-04-08 (2 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `journal_entries`

- **object type:** table  |  **size:** 10080 kB
- **counted rows (M.006):** 14236
- **exported rows:** 14236  (matches)
- **export file:** manifest key `T.journal_entries`
- **columns (11):** id, organization_id, entry_date, period, description, source_table, source_id, is_reversal_of, posted_at, posted_by, metadata
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (3):** is_reversal_of -> journal_entries.id [RESTRICT]; organization_id -> organizations.id [CASCADE]; posted_by -> users.id [NO ACTION]
- **date coverage:** entry_date 2019-11-03..2026-09-20 (54 mo); posted_at 2026-04-25..2026-08-29 (5 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **Yes - primary ledger evidence.** Reversal and soft-delete handling mandatory.

### `journal_lines`

- **object type:** table  |  **size:** 17 MB
- **counted rows (M.006):** 33894
- **exported rows:** 33894  (matches)
- **export file:** manifest key `T.journal_lines`
- **export note:** base table DENORMALISED: +6 cols joined from journal_entries (entry_date, period, posted_at, source_table, source_id, is_reversal_of)
- **columns (14):** id, journal_entry_id, organization_id, account_id, debit, credit, party_kind, party_id, allotment_id, property_id, apartment_id, bed_id, memo, line_no
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (6):** account_id -> coa_accounts.id [RESTRICT]; allotment_id -> tenant_allotments.id [RESTRICT]; apartment_id -> apartments.id [NO ACTION]; bed_id -> beds.id [NO ACTION]; journal_entry_id -> journal_entries.id [CASCADE]; property_id -> properties.id [NO ACTION]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **Yes - primary ledger evidence.** Reversal and soft-delete handling mandatory.

### `leave_requests_sync`

- **object type:** table  |  **size:** 24 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (10):** id, record_id, employee_name, leave_type, start_date, end_date, reason, status, synced_at, created_at
- **organization_id:** absent
- **foreign keys:** none declared
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `ledger_entries`

- **object type:** table  |  **size:** 120 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (9):** id, organization_id, asset_id, entry_type, amount, entry_date, reference, notes, created_at
- **organization_id:** present; distinct_orgs=0, null_org_rows=0
- **foreign keys (1):** asset_id -> assets.id [CASCADE]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `lifecycle_config`

- **object type:** table  |  **size:** 24 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (15):** id, organization_id, from_date, to_date, booking_fee, onboarding_fee, advance_ratio, exit_fee_under_1yr, key_loss_fee, notice_period_days, refund_deadline_days, created_at, gst_exemption_days, gst_short_stay_rate, gst_rcm_rate
- **organization_id:** present; distinct_orgs=0, null_org_rows=0
- **foreign keys (1):** organization_id -> organizations.id [NO ACTION]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `maintenance_item_stock_entries`

- **object type:** table  |  **size:** 48 kB
- **counted rows (M.006):** 47
- **exported rows:** 47  (matches)
- **export file:** manifest key `T.maintenance_item_stock_entries`
- **columns (12):** id, organization_id, maintenance_item_id, quantity_received, quantity_available, purchase_cost_per_unit, vendor_name, invoice_number, purchased_on, remarks, created_by, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** maintenance_item_id -> maintenance_items.id [CASCADE]; organization_id -> organizations.id [CASCADE]
- **date coverage:** created_at 2026-04-22..2026-08-20 (5 mo); purchased_on 2026-04-21..2026-08-20 (5 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `maintenance_item_usage`

- **object type:** table  |  **size:** 80 kB
- **counted rows (M.006):** 39
- **exported rows:** 39  (matches)
- **export file:** manifest key `T.maintenance_item_usage`
- **columns (12):** id, organization_id, maintenance_ticket_id, maintenance_item_id, stock_entry_id, quantity_used, cost_per_unit, total_cost, usage_source, remarks, created_by, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (4):** maintenance_item_id -> maintenance_items.id [CASCADE]; maintenance_ticket_id -> maintenance_tickets.id [CASCADE]; organization_id -> organizations.id [CASCADE]; stock_entry_id -> maintenance_item_stock_entries.id [SET NULL]
- **date coverage:** created_at 2026-04-24..2026-08-20 (5 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `maintenance_items`

- **object type:** table  |  **size:** 208 kB
- **counted rows (M.006):** 93
- **exported rows:** 93  (matches)
- **export file:** manifest key `T.maintenance_items`
- **columns (16):** id, organization_id, name, specifications, default_unit_cost, active, created_at, updated_at, item_name, item_code, unit, default_cost, minimum_stock_level, is_active, asset_type_id, issue_type_id
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (3):** asset_type_id -> asset_types.id [RESTRICT]; issue_type_id -> issue_types.id [SET NULL]; organization_id -> organizations.id [CASCADE]
- **date coverage:** created_at 2026-04-22..2026-07-17 (4 mo); updated_at 2026-04-22..2026-07-17 (4 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `maintenance_tickets`

- **object type:** table  |  **size:** 2200 kB
- **counted rows (M.006):** 1610
- **exported rows:** 1611  **(delta +1 vs M.006)**
- **export file:** manifest key `T.maintenance_tickets`
- **export note:** base table; photo_urls/tenant_name/tenant_phone EXCLUDED; +1 row vs M.006 (live write)
- **columns (30):** id, organization_id, ticket_number, tenant_id, property_id, apartment_id, bed_id, issue_type_id, description, photo_urls, priority, status, assigned_to, sla_deadline, resolved_at, closed_at, tenant_approved, diagnostic_data, created_at, tenant_rejection_reason, tenant_name, tenant_phone, created_by, updated_at, resolution_id, asset_id, issue_sub_type_id, resolution_edit_unlocked_at, resolution_edit_unlocked_by, closure_cost
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (11):** apartment_id -> apartments.id [NO ACTION]; asset_id -> assets.id [SET NULL]; assigned_to -> users.id [NO ACTION]; bed_id -> beds.id [NO ACTION]; created_by -> users.id [NO ACTION]; issue_sub_type_id -> issue_sub_types.id [SET NULL]; issue_type_id -> issue_types.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]; property_id -> properties.id [NO ACTION]; resolution_id -> ticket_resolutions.id [SET NULL]; tenant_id -> tenants.id [NO ACTION]
- **date coverage:** closed_at 2025-01-29..2026-08-29 (20 mo); created_at 2025-01-29..2026-08-29 (20 mo); resolution_edit_unlocked_at 2026-06-21..2026-07-16 (2 mo); resolved_at 2025-01-29..2026-08-27 (20 mo); sla_deadline 2025-02-01..2026-09-01 (20 mo); updated_at 2026-03-31..2026-08-29 (6 mo)
- **sensitivity:** EXCLUDED: photo_urls | HASHED: tenant_phone
- **analytics suitability:** Supporting / operational.

### `migration_log`

- **object type:** table  |  **size:** 16 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (8):** id, run_at, table_name, record_id, action, source_file, source_row, notes
- **organization_id:** absent
- **foreign keys:** none declared
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `offline_kyc_pending`

- **object type:** table  |  **size:** 240 kB
- **counted rows (M.006):** 38
- **exported rows:** 38  (matches)
- **export file:** manifest key `T.offline_kyc_pending`
- **columns (19):** id, organization_id, allotment_id, tenant_id, access_token, status, registration_data, form_payload, kyc_front_path, kyc_back_path, final_pdf_path, sent_to_email, sent_to_phone, submitted_at, merged_at, created_by, created_at, updated_at, expires_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (4):** allotment_id -> tenant_allotments.id [CASCADE]; created_by -> users.id [SET NULL]; organization_id -> organizations.id [CASCADE]; tenant_id -> tenants.id [CASCADE]
- **date coverage:** created_at 2026-06-25..2026-08-28 (3 mo); expires_at 2026-07-09..2026-08-29 (2 mo); submitted_at 2026-06-25..2026-08-28 (3 mo); updated_at 2026-06-26..2026-08-28 (3 mo)
- **sensitivity:** EXCLUDED: access_token, final_pdf_path, kyc_back_path, kyc_front_path | HASHED: sent_to_email, sent_to_phone
- **analytics suitability:** Supporting / operational.

### `org_ai_settings`

- **object type:** table  |  **size:** 16 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (5):** organization_id, payment_proof_mode, meter_reading_mode, created_at, updated_at
- **organization_id:** present; distinct_orgs=0, null_org_rows=0
- **foreign keys:** none declared
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `org_branding_settings`

- **object type:** table  |  **size:** 32 kB
- **counted rows (M.006):** 1
- **exported rows:** 1  (matches)
- **export file:** manifest key `T.org_branding_settings`
- **columns (8):** organization_id, logo_url, address_text, footer_text, contact_email, contact_phone, created_at, updated_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (1):** organization_id -> organizations.id [CASCADE]
- **date coverage:** created_at 2026-04-21..2026-04-21 (1 mo); updated_at 2026-05-29..2026-05-29 (1 mo)
- **sensitivity:** HASHED: contact_email, contact_phone
- **analytics suitability:** Supporting / operational.

### `org_email_settings`

- **object type:** table  |  **size:** 32 kB
- **counted rows (M.006):** 1
- **exported rows:** 1  (matches)
- **export file:** manifest key `T.org_email_settings`
- **columns (18):** organization_id, enabled, smtp_host, smtp_port, smtp_secure, smtp_user, smtp_pass_encrypted, from_name, from_email, reply_to, imap_host, imap_port, imap_secure, pop3_host, pop3_port, pop3_secure, created_at, updated_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (1):** organization_id -> organizations.id [CASCADE]
- **date coverage:** created_at 2026-04-20..2026-04-20 (1 mo); updated_at 2026-06-10..2026-06-10 (1 mo)
- **sensitivity:** EXCLUDED: smtp_pass_encrypted | HASHED: from_email
- **analytics suitability:** Supporting / operational.

### `org_whatsapp_settings`

- **object type:** table  |  **size:** 64 kB
- **counted rows (M.006):** 1
- **exported rows:** 1  (matches)
- **export file:** manifest key `T.org_whatsapp_settings`
- **columns (9):** organization_id, test_phone, test_mode_enabled, created_at, updated_at, notifications_enabled, post_invoice_whatsapp_modal_enabled, post_collection_whatsapp_modal_enabled, ai_auto_response_enabled
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (1):** organization_id -> organizations.id [CASCADE]
- **date coverage:** created_at 2026-05-12..2026-05-12 (1 mo); updated_at 2026-08-08..2026-08-08 (1 mo)
- **sensitivity:** HASHED: test_phone
- **analytics suitability:** Supporting / operational.

### `organization_bank_accounts`

- **object type:** table  |  **size:** 56 kB
- **counted rows (M.006):** 5
- **exported rows:** 5  (matches)
- **export file:** manifest key `T.organization_bank_accounts`
- **columns (15):** id, organization_id, bank_name, account_name, account_number, ifsc_code, branch, account_type, swift_code, upi_id, is_primary, status, notes, created_at, upi_ids
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (1):** organization_id -> organizations.id [NO ACTION]
- **date coverage:** created_at 2026-03-17..2026-03-25 (1 mo)
- **sensitivity:** HASHED: account_number, ifsc_code, upi_id, upi_ids
- **analytics suitability:** Supporting / operational.

### `organization_subscriptions`

- **object type:** table  |  **size:** 48 kB
- **counted rows (M.006):** 1
- **exported rows:** 1  (matches)
- **export file:** manifest key `T.organization_subscriptions`
- **columns (14):** id, organization_id, plan_id, status, billing_cycle, current_period_start, current_period_end, trial_ends_at, razorpay_subscription_id, razorpay_customer_id, cancelled_at, cancel_reason, created_at, updated_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** organization_id -> organizations.id [NO ACTION]; plan_id -> subscription_plans.id [NO ACTION]
- **date coverage:** created_at 2026-04-05..2026-04-05 (1 mo); current_period_end 2027-04-05..2027-04-05 (1 mo); current_period_start 2026-04-05..2026-04-05 (1 mo); updated_at 2026-04-05..2026-04-05 (1 mo)
- **sensitivity:** HASHED: razorpay_customer_id, razorpay_subscription_id
- **analytics suitability:** Supporting / operational.

### `organizations`

- **object type:** table  |  **size:** 32 kB
- **counted rows (M.006):** 1
- **exported rows:** 1  (matches)
- **export file:** manifest key `T.organizations`
- **columns (22):** id, organization_name, subscription_plan, created_at, gst_number, onboarding_completed, onboarding_step, ticket_auto_approve_threshold, ticket_repeat_check_days, exit_task_assignee_1, exit_task_assignee_2, logo_url, address_line1, address_line2, city, state, pincode, country, contact_person_name, contact_phone, contact_email, website
- **organization_id:** absent
- **foreign keys:** none declared
- **date coverage:** created_at 2026-03-16..2026-03-16 (1 mo)
- **sensitivity:** HASHED: contact_email, contact_phone, gst_number
- **analytics suitability:** Supporting / operational.

### `otp_codes`

- **object type:** table  |  **size:** 80 kB
- **counted rows (M.006):** 6
- **exported rows:** 6  (matches)
- **export file:** manifest key `T.otp_codes`
- **columns (6):** id, phone, otp_code, expires_at, verified, created_at
- **organization_id:** absent
- **foreign keys:** none declared
- **date coverage:** created_at 2026-07-03..2026-08-19 (2 mo); expires_at 2026-07-03..2026-08-19 (2 mo)
- **sensitivity:** EXCLUDED: otp_code | HASHED: phone
- **analytics suitability:** Supporting / operational.

### `owner_contracts`

- **object type:** table  |  **size:** 96 kB
- **counted rows (M.006):** 35
- **exported rows:** 35  (matches)
- **export file:** manifest key `T.owner_contracts`
- **columns (32):** id, organization_id, owner_id, property_id, contract_type, start_date, end_date, monthly_rent, revenue_share_percentage, security_deposit, lock_in_months, escalation_percentage, escalation_interval_months, payment_due_day, agreement_url, notes, status, created_at, property_tax_id, water_tax_details, payment_schedule, renewal_date, renewal_periods, ownership_doc_url, apartment_id, property_tax_amount, property_tax_frequency, water_tax_id, water_tax_amount, water_tax_frequency, rent_paid_in_advance, gst_info
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (4):** apartment_id -> apartments.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]; owner_id -> owners.id [CASCADE]; property_id -> properties.id [NO ACTION]
- **date coverage:** created_at 2026-04-01..2026-04-17 (1 mo); end_date 2025-03-31..2032-03-31 (10 mo); renewal_date 2024-12-31..2031-12-31 (10 mo); start_date 2022-10-01..2025-08-01 (9 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **Yes - primary financial evidence.**

### `owner_payments`

- **object type:** table  |  **size:** 336 kB
- **counted rows (M.006):** 345
- **exported rows:** 345  (matches)
- **export file:** manifest key `T.owner_payments`
- **columns (18):** id, organization_id, owner_id, contract_id, apartment_id, payment_month, due_date, base_amount, escalated_amount, status, paid_date, payment_mode, notes, created_at, actual_due_date, reference_number, bill_date, bank_account_id
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (5):** apartment_id -> apartments.id [NO ACTION]; bank_account_id -> organization_bank_accounts.id [SET NULL]; contract_id -> owner_contracts.id [CASCADE]; organization_id -> organizations.id [NO ACTION]; owner_id -> owners.id [CASCADE]
- **date coverage:** actual_due_date 2022-11-09..2026-08-09 (46 mo); bill_date 2022-11-01..2026-08-01 (46 mo); created_at 2026-08-13..2026-08-13 (1 mo); due_date 2022-11-09..2026-08-09 (46 mo); paid_date 2023-11-05..2026-08-10 (25 mo)
- **sensitivity:** HASHED: bank_account_id
- **analytics suitability:** **Yes - primary financial evidence.**

### `owners`

- **object type:** table  |  **size:** 32 kB
- **counted rows (M.006):** 13
- **exported rows:** 13  (matches)
- **export file:** manifest key `T.owners`
- **columns (20):** id, organization_id, full_name, phone, email, pan_number, aadhar_number, address, city, state, pincode, bank_name, bank_account_number, bank_ifsc, gst_number, photo_url, id_proof_url, notes, created_at, status
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (1):** organization_id -> organizations.id [NO ACTION]
- **date coverage:** created_at 2025-06-28..2025-06-28 (1 mo)
- **sensitivity:** EXCLUDED: id_proof_url, photo_url | HASHED: aadhar_number, bank_account_number, bank_ifsc, email, gst_number, pan_number, phone | kept-but-flagged: full_name
- **analytics suitability:** Supporting / operational.

### `payment_proofs`

- **object type:** table  |  **size:** 64 kB
- **counted rows (M.006):** 24
- **exported rows:** 24  (matches)
- **export file:** manifest key `T.payment_proofs`
- **columns (9):** id, organization_id, context, booking_id, tenant_id, file_url, extracted, created_by, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** organization_id -> organizations.id [NO ACTION]; tenant_id -> tenants.id [NO ACTION]
- **date coverage:** created_at 2026-08-07..2026-08-29 (1 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `payroll`

- **object type:** table  |  **size:** 40 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (26):** id, employee_id, company_id, month, year, base_salary, days_worked, total_days, non_working_days, leave_days, approved_leave_days, rejected_leave_days, half_days, working_days_month, absent_days, hours_worked, overtime_hours, overtime_pay, deductions, net_salary, bonus, status, paid_date, payment_mode, payment_reference, created_at
- **organization_id:** absent
- **foreign keys (2):** company_id -> companies.id [SET NULL]; employee_id -> employees.id [CASCADE]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `payroll_sync`

- **object type:** table  |  **size:** 64 kB
- **counted rows (M.006):** 18
- **exported rows:** 18  (matches)
- **export file:** manifest key `T.payroll_sync`
- **columns (17):** id, email, employee_name, team_member_id, organization_id, period_start, period_end, monthly_salary, per_day_salary, present_days, leave_days, absent_days, paid_leave_days, deducted_days, deduction_amount, payable_salary, synced_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=6 **<- NULL org rows present**
- **foreign keys:** none declared
- **date coverage:** period_end 2026-06-28..2026-06-28 (1 mo); period_start 2026-05-29..2026-05-29 (1 mo); synced_at 2026-06-29..2026-06-29 (1 mo)
- **sensitivity:** HASHED: email
- **analytics suitability:** Supporting / operational.

### `profiles`

- **object type:** table  |  **size:** 104 kB
- **counted rows (M.006):** 222
- **exported rows:** 223  **(delta +1 vs M.006)**
- **export file:** manifest key `T.profiles`
- **export note:** base table; avatar_url/email/full_name/phone EXCLUDED; +1 row vs M.006 (live write)
- **columns (8):** id, phone, full_name, email, avatar_url, organization_id, created_at, updated_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** id -> users.id [CASCADE]; organization_id -> organizations.id [NO ACTION]
- **date coverage:** created_at 2026-03-16..2026-08-29 (6 mo); updated_at 2026-03-16..2026-08-29 (6 mo)
- **sensitivity:** EXCLUDED: avatar_url | HASHED: email, phone | kept-but-flagged: full_name
- **analytics suitability:** Supporting / operational.

### `properties`

- **object type:** table  |  **size:** 80 kB
- **counted rows (M.006):** 1
- **exported rows:** 1  (matches)
- **export file:** manifest key `T.properties`
- **columns (15):** id, organization_id, property_name, address, city, state, pincode, status, created_at, gps_latitude, gps_longitude, photo_urls, code, start_date, kyc_qr_code
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (1):** organization_id -> organizations.id [NO ACTION]
- **date coverage:** created_at 2026-03-16..2026-03-16 (1 mo); start_date 2023-04-01..2023-04-01 (1 mo)
- **sensitivity:** EXCLUDED: photo_urls
- **analytics suitability:** **Yes - primary occupancy/tenancy evidence.**

### `property_images`

- **object type:** table  |  **size:** 64 kB
- **counted rows (M.006):** 2
- **exported rows:** 2  (matches)
- **export file:** manifest key `T.property_images`
- **columns (8):** id, organization_id, property_id, image_url, caption, display_order, is_cover, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** organization_id -> organizations.id [CASCADE]; property_id -> properties.id [CASCADE]
- **date coverage:** created_at 2026-05-22..2026-05-22 (1 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `purchase_items`

- **object type:** table  |  **size:** 16 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (7):** id, purchase_order_id, asset_type_id, quantity, unit_price, created_at, organization_id
- **organization_id:** present; distinct_orgs=0, null_org_rows=0
- **foreign keys (2):** asset_type_id -> asset_types.id [NO ACTION]; purchase_order_id -> purchase_orders.id [CASCADE]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `purchase_orders`

- **object type:** table  |  **size:** 16 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (8):** id, organization_id, vendor_id, order_date, total_cost, invoice_number, status, created_at
- **organization_id:** present; distinct_orgs=0, null_org_rows=0
- **foreign keys (2):** organization_id -> organizations.id [NO ACTION]; vendor_id -> vendors.id [NO ACTION]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `receipt_allocations`

- **object type:** table  |  **size:** 40 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (9):** id, organization_id, receipt_id, invoice_id, adjustment_id, amount, allocated_at, allocated_by, notes
- **organization_id:** present; distinct_orgs=0, null_org_rows=0
- **foreign keys (5):** adjustment_id -> tenant_adjustments.id [RESTRICT]; allocated_by -> users.id [NO ACTION]; invoice_id -> invoices.id [RESTRICT]; organization_id -> organizations.id [CASCADE]; receipt_id -> receipts.id [CASCADE]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `receipt_number_counters`

- **object type:** table  |  **size:** 64 kB
- **counted rows (M.006):** 8
- **exported rows:** 8  (matches)
- **export file:** manifest key `T.receipt_number_counters`
- **columns (6):** organization_id, property_id, fy, month, last_seq, updated_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys:** none declared
- **date coverage:** updated_at 2026-05-20..2026-08-29 (4 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `receipts`

- **object type:** table  |  **size:** 3904 kB
- **counted rows (M.006):** 5858
- **exported rows:** 5858  (matches)
- **export file:** manifest key `T.receipts`
- **columns (17):** id, organization_id, payment_date, payment_mode, amount_paid, created_at, receipt_number, bank_account_id, reference_number, tenant_allotment_id, tenant_id, receipt_type, base_amount, processing_fee, is_deleted, is_locked, locked_by
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (4):** bank_account_id -> organization_bank_accounts.id [SET NULL]; organization_id -> organizations.id [NO ACTION]; tenant_allotment_id -> tenant_allotments.id [NO ACTION]; tenant_id -> tenants.id [NO ACTION]
- **date coverage:** created_at 2026-03-28..2026-08-29 (6 mo); payment_date 2022-11-30..2026-08-28 (46 mo)
- **sensitivity:** HASHED: bank_account_id
- **analytics suitability:** **Yes - primary financial evidence.**

### `receipts_dedup_audit`

- **object type:** table  |  **size:** 32 kB
- **counted rows (M.006):** 9
- **exported rows:** 9  (matches)
- **export file:** manifest key `T.receipts_dedup_audit`
- **columns (9):** id, organization_id, tenant_id, payment_date, amount_paid, reference_number, duplicate_count, receipt_ids, detected_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys:** none declared
- **date coverage:** detected_at 2026-04-22..2026-04-22 (1 mo); payment_date 2023-09-02..2026-04-04 (9 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `regular_maintenance_rules`

- **object type:** table  |  **size:** 16 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (15):** id, organization_id, issue_type_id, maintenance_type, frequency, asset_type_id, property_id, apartment_id, start_date, last_run_at, next_run_at, is_active, auto_assign, created_by, created_at
- **organization_id:** present; distinct_orgs=0, null_org_rows=0
- **foreign keys (5):** apartment_id -> apartments.id [NO ACTION]; asset_type_id -> asset_types.id [NO ACTION]; issue_type_id -> issue_types.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]; property_id -> properties.id [NO ACTION]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `replacement_forecasts`

- **object type:** table  |  **size:** 24 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (7):** id, asset_id, expected_replacement_date, replacement_cost, urgency_level, created_at, organization_id
- **organization_id:** present; distinct_orgs=0, null_org_rows=0
- **foreign keys (1):** asset_id -> assets.id [CASCADE]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `role_permissions`

- **object type:** table  |  **size:** 96 kB
- **counted rows (M.006):** 122
- **exported rows:** 122  (matches)
- **export file:** manifest key `T.role_permissions`
- **columns (10):** id, organization_id, role, module, can_create, can_read, can_update, can_delete, created_at, updated_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (1):** organization_id -> organizations.id [CASCADE]
- **date coverage:** created_at 2026-03-19..2026-07-18 (5 mo); updated_at 2026-03-19..2026-07-18 (5 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `room_switches`

- **object type:** table  |  **size:** 128 kB
- **counted rows (M.006):** 34
- **exported rows:** 34  (matches)
- **export file:** manifest key `T.room_switches`
- **columns (28):** id, organization_id, tenant_id, allotment_id, old_bed_id, new_bed_id, switch_type, switch_date, effective_date, rent_difference, adjustment_type, status, notes, created_at, old_allotment_id, new_allotment_id, old_property_id, new_property_id, old_apartment_id, new_apartment_id, old_rent, new_rent, deposit_difference, eb_charges, completed_at, cancelled_at, completed_by, cancelled_by
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (7):** allotment_id -> tenant_allotments.id [NO ACTION]; new_allotment_id -> tenant_allotments.id [NO ACTION]; new_bed_id -> beds.id [NO ACTION]; old_allotment_id -> tenant_allotments.id [NO ACTION]; old_bed_id -> beds.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]; tenant_id -> tenants.id [NO ACTION]
- **date coverage:** cancelled_at 2026-05-27..2026-07-17 (2 mo); completed_at 2026-05-17..2026-08-25 (4 mo); created_at 2026-05-17..2026-08-25 (4 mo); effective_date 2026-05-01..2026-08-28 (4 mo); switch_date 2026-05-16..2026-08-28 (4 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **Yes - primary occupancy/tenancy evidence.**

### `running_bed_maintenance_details`

- **object type:** table  |  **size:** 112 kB
- **counted rows (M.006):** 23
- **exported rows:** 23  (matches)
- **export file:** manifest key `T.running_bed_maintenance_details`
- **columns (22):** id, organization_id, ticket_id, purchase_id, tenant_id, bed_id, apartment_id, property_id, item_name, quantity, unit_price, actual_cost, vendor_name, cost_scope, distributed_amount, billing_month, maintenance_type, parts_details, diagnosis_summary, notes, created_at, distributed_beds
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (6):** apartment_id -> apartments.id [NO ACTION]; bed_id -> beds.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]; property_id -> properties.id [NO ACTION]; tenant_id -> tenants.id [NO ACTION]; ticket_id -> maintenance_tickets.id [CASCADE]
- **date coverage:** created_at 2026-04-24..2026-08-24 (5 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `subscription_plans`

- **object type:** table  |  **size:** 48 kB
- **counted rows (M.006):** 4
- **exported rows:** 4  (matches)
- **export file:** manifest key `T.subscription_plans`
- **columns (15):** id, plan_name, display_name, description, price_monthly, price_yearly, max_properties, max_apartments, max_beds, max_users, max_tenants, feature_flags, is_active, sort_order, created_at
- **organization_id:** absent
- **foreign keys:** none declared
- **date coverage:** created_at 2026-04-05..2026-04-05 (1 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `tab_permissions`

- **object type:** table  |  **size:** 224 kB
- **counted rows (M.006):** 405
- **exported rows:** 405  (matches)
- **export file:** manifest key `T.tab_permissions`
- **columns (12):** id, organization_id, role, module, tab_key, is_visible, created_at, updated_at, can_create, can_read, can_update, can_delete
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (1):** organization_id -> organizations.id [NO ACTION]
- **date coverage:** created_at 2026-03-23..2026-06-24 (4 mo); updated_at 2026-03-23..2026-06-30 (4 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `team_attendance`

- **object type:** table  |  **size:** 976 kB
- **counted rows (M.006):** 1320
- **exported rows:** 1320  (matches)
- **export file:** manifest key `T.team_attendance`
- **columns (13):** id, organization_id, team_member_id, date, status, check_in, check_out, notes, created_at, email, convex_record_id, attendance_id, overtime_hours
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** organization_id -> organizations.id [NO ACTION]; team_member_id -> team_members.id [CASCADE]
- **date coverage:** created_at 2026-04-22..2026-08-29 (5 mo); date 2026-03-11..2026-08-29 (6 mo)
- **sensitivity:** HASHED: email
- **analytics suitability:** Supporting / operational.

### `team_departments`

- **object type:** table  |  **size:** 48 kB
- **counted rows (M.006):** 4
- **exported rows:** 4  (matches)
- **export file:** manifest key `T.team_departments`
- **columns (7):** id, organization_id, name, is_deleted, created_at, updated_at, attendance_exempt
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (1):** organization_id -> organizations.id [NO ACTION]
- **date coverage:** created_at 2026-07-23..2026-07-23 (1 mo); updated_at 2026-07-23..2026-07-23 (1 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `team_members`

- **object type:** table  |  **size:** 32 kB
- **counted rows (M.006):** 20
- **exported rows:** 20  (matches)
- **export file:** manifest key `T.team_members`
- **columns (37):** id, organization_id, user_id, first_name, last_name, gender, phone, email, date_of_birth, designation, department, joining_date, id_proof_type, id_proof_number, id_proof_url, photo_url, pan_number, aadhar_number, address, city, state, pincode, bank_name, bank_account_number, bank_ifsc, emergency_contact_name, emergency_contact_phone, salary_amount, status, created_at, exit_date, exit_type, exit_reason, free_leave_days, department_id, work_start_time, work_hours_per_day
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (3):** department_id -> team_departments.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]; user_id -> users.id [NO ACTION]
- **date coverage:** created_at 2026-03-17..2026-07-07 (4 mo); date_of_birth 1976-07-25..2001-07-13 (2 mo); exit_date 2026-02-11..2026-08-04 (4 mo); joining_date 2024-11-05..2026-03-28 (3 mo)
- **sensitivity:** EXCLUDED: id_proof_url, photo_url | HASHED: aadhar_number, bank_account_number, bank_ifsc, email, emergency_contact_phone, id_proof_number, pan_number, phone | kept-but-flagged: date_of_birth, emergency_contact_name, first_name, last_name
- **analytics suitability:** Supporting / operational.

### `team_payments`

- **object type:** table  |  **size:** 96 kB
- **counted rows (M.006):** 3
- **exported rows:** 3  (matches)
- **export file:** manifest key `T.team_payments`
- **columns (10):** id, organization_id, team_member_id, payment_type, amount, payment_date, payment_month, payment_mode, notes, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** organization_id -> organizations.id [NO ACTION]; team_member_id -> team_members.id [CASCADE]
- **date coverage:** created_at 2026-05-15..2026-05-15 (1 mo); payment_date 2026-03-27..2026-04-27 (2 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `team_salary_bills`

- **object type:** table  |  **size:** 80 kB
- **counted rows (M.006):** 71
- **exported rows:** 71  (matches)
- **export file:** manifest key `T.team_salary_bills`
- **columns (14):** id, organization_id, team_member_id, month, working_days, present_days, base_salary, earned_salary, advance_deducted, other_deductions, net_payable, status, notes, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** organization_id -> organizations.id [NO ACTION]; team_member_id -> team_members.id [NO ACTION]
- **date coverage:** created_at 2026-05-15..2026-08-28 (4 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `tenant_absence_records`

- **object type:** table  |  **size:** 32 kB
- **counted rows (M.006):** 38
- **exported rows:** 38  (matches)
- **export file:** manifest key `T.tenant_absence_records`
- **columns (9):** id, organization_id, tenant_id, allotment_id, from_date, to_date, reason, created_by, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (3):** allotment_id -> tenant_allotments.id [SET NULL]; organization_id -> organizations.id [NO ACTION]; tenant_id -> tenants.id [CASCADE]
- **date coverage:** created_at 2026-04-01..2026-08-25 (5 mo); from_date 2026-02-07..2026-08-24 (7 mo); to_date 2026-03-09..2026-09-21 (7 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `tenant_adjustments`

- **object type:** table  |  **size:** 208 kB
- **counted rows (M.006):** 266
- **exported rows:** 266  (matches)
- **export file:** manifest key `T.tenant_adjustments`
- **columns (21):** id, organization_id, tenant_id, allotment_id, adjustment_type, amount, reason, reference_number, adjustment_date, billing_month, property_id, apartment_id, bed_id, created_by, created_at, is_deleted, category, reference_type, reference_id, is_locked, locked_by
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (6):** allotment_id -> tenant_allotments.id [NO ACTION]; apartment_id -> apartments.id [NO ACTION]; bed_id -> beds.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]; property_id -> properties.id [NO ACTION]; tenant_id -> tenants.id [NO ACTION]
- **date coverage:** adjustment_date 2021-12-05..2026-08-25 (43 mo); created_at 2026-03-28..2026-08-21 (6 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **Yes - primary financial evidence.**

### `tenant_allotments`

- **object type:** table  |  **size:** 1504 kB
- **counted rows (M.006):** 1213
- **exported rows:** 1213  (matches)
- **export file:** manifest key `T.tenant_allotments`
- **columns (28):** id, organization_id, tenant_id, property_id, apartment_id, bed_id, booking_date, onboarding_date, estimated_exit_date, actual_exit_date, monthly_rental, deposit_paid, discount, staying_status, created_at, notice_date, onboarding_charges, prorated_rent, total_due, paid_amount, balance_due, payment_status, expected_payment_date, kyc_front_url, kyc_back_url, premium, processing_fee, expected_stay_days
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (5):** apartment_id -> apartments.id [NO ACTION]; bed_id -> beds.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]; property_id -> properties.id [NO ACTION]; tenant_id -> tenants.id [CASCADE]
- **date coverage:** actual_exit_date 2022-11-20..2026-09-20 (47 mo); booking_date 2019-11-03..2026-08-28 (67 mo); created_at 2026-03-28..2026-08-28 (6 mo); estimated_exit_date 2022-11-02..2026-09-27 (47 mo); notice_date 2022-11-02..2026-08-28 (46 mo); onboarding_date 2019-11-03..2026-08-31 (67 mo)
- **sensitivity:** EXCLUDED: kyc_back_url, kyc_front_url
- **analytics suitability:** **Yes - primary occupancy/tenancy evidence.**

### `tenant_document_history`

- **object type:** table  |  **size:** 64 kB
- **counted rows (M.006):** 1
- **exported rows:** 1  (matches)
- **export file:** manifest key `T.tenant_document_history`
- **columns (9):** id, organization_id, tenant_id, allotment_id, doc_slot, old_url, new_url, replaced_at, replaced_by
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** allotment_id -> tenant_allotments.id [NO ACTION]; tenant_id -> tenants.id [NO ACTION]
- **date coverage:** replaced_at 2026-07-25..2026-07-25 (1 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `tenant_exits`

- **object type:** table  |  **size:** 552 kB
- **counted rows (M.006):** 147
- **exported rows:** 147  (matches)
- **export file:** manifest key `T.tenant_exits`
- **columns (25):** id, organization_id, tenant_id, allotment_id, bed_id, exit_date, has_notice, room_inspection, key_returned, damage_charges, key_loss_fee, exit_charges, eb_charges, pending_rent, total_deductions, advance_held, refund_due, refund_status, refund_date, notes, created_at, is_deleted, refund_reference, refund_bank_id, refund_proof_url
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (4):** allotment_id -> tenant_allotments.id [NO ACTION]; bed_id -> beds.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]; tenant_id -> tenants.id [NO ACTION]
- **date coverage:** created_at 2026-03-28..2026-08-28 (6 mo); exit_date 2023-07-10..2026-09-20 (31 mo); refund_date 2023-09-05..2026-08-26 (18 mo)
- **sensitivity:** EXCLUDED: refund_proof_url
- **analytics suitability:** **Yes - primary occupancy/tenancy evidence.**

### `tenant_notices`

- **object type:** table  |  **size:** 208 kB
- **counted rows (M.006):** 86
- **exported rows:** 86  (matches)
- **export file:** manifest key `T.tenant_notices`
- **columns (11):** id, organization_id, tenant_id, allotment_id, bed_id, notice_date, exit_date, actual_exit_date, status, notes, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (4):** allotment_id -> tenant_allotments.id [NO ACTION]; bed_id -> beds.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]; tenant_id -> tenants.id [NO ACTION]
- **date coverage:** created_at 2026-04-01..2026-08-27 (5 mo); exit_date 2026-04-16..2026-09-27 (6 mo); notice_date 2026-04-01..2026-08-28 (5 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **Yes - primary occupancy/tenancy evidence.**

### `tenant_remarks`

- **object type:** table  |  **size:** 48 kB
- **counted rows (M.006):** 2
- **exported rows:** 2  (matches)
- **export file:** manifest key `T.tenant_remarks`
- **columns (9):** id, organization_id, tenant_id, remark_type, title, description, severity, created_by, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (1):** tenant_id -> tenants.id [CASCADE]
- **date coverage:** created_at 2026-08-11..2026-08-11 (1 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `tenant_transactions`

- **object type:** table  |  **size:** 14 MB
- **counted rows (M.006):** 16451
- **exported rows:** 16451  (matches)
- **export file:** manifest key `T.tenant_transactions`
- **columns (14):** id, tenant_id, allotment_id, date, amount, direction, ledger_type, category, reference_table, reference_id, description, metadata, organization_id, created_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (3):** allotment_id -> tenant_allotments.id [CASCADE]; organization_id -> organizations.id [NO ACTION]; tenant_id -> tenants.id [CASCADE]
- **date coverage:** created_at 2026-04-17..2026-04-28 (1 mo); date 0206-03-27..2026-05-05 (65 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **Yes - primary financial evidence.**

### `tenants`

- **object type:** table  |  **size:** 1568 kB
- **counted rows (M.006):** 1027
- **exported rows:** 1027  (matches)
- **export file:** manifest key `T.tenants`
- **export note:** base table; 27 PII cols EXCLUDED, phone_hash derived
- **columns (54):** id, organization_id, user_id, full_name, phone, email, date_of_birth, gender, id_proof_type, id_proof_number, id_proof_url, permanent_address, company_name, company_address, designation, emergency_contact_name, emergency_contact_phone, photo_url, kyc_completed, created_at, first_name, last_name, staying_status, food_preference, relation_type, relation_name, city, pincode, state, age, profession, company_city, company_pincode, company_state, date_of_joining, course, id_card_url, emergency_contact_relationship, bank_name, bank_branch, bank_account_number, bank_account_holder, bank_ifsc, aadhar_number, pan_number, gst_number, gst_name, aadhar_image_url, address, emergency_contact_relation, tenant_rating, rating_last_computed, property_id, upi_id
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (4):** organization_id -> organizations.id [NO ACTION]; organization_id -> properties.organization_id [RESTRICT]; property_id -> properties.id [RESTRICT]; user_id -> users.id [NO ACTION]
- **date coverage:** created_at 2025-05-05..2026-08-27 (7 mo); date_of_birth 1959-05-14..2026-06-13 (218 mo); date_of_joining 2023-06-14..2026-09-02 (15 mo); rating_last_computed 2026-08-03..2026-08-11 (1 mo)
- **sensitivity:** EXCLUDED: aadhar_image_url, id_card_url, id_proof_url, photo_url | HASHED: aadhar_number, bank_account_holder, bank_account_number, bank_ifsc, email, emergency_contact_phone, gst_number, id_proof_number, pan_number, phone, upi_id | kept-but-flagged: date_of_birth, emergency_contact_name, emergency_contact_relation, emergency_contact_relationship, first_name, full_name, last_name, permanent_address
- **analytics suitability:** **Yes - primary occupancy/tenancy evidence.**

### `ticket_assignment_rules`

- **object type:** table  |  **size:** 32 kB
- **counted rows (M.006):** 7
- **exported rows:** 7  (matches)
- **export file:** manifest key `T.ticket_assignment_rules`
- **columns (8):** id, issue_type_id, assigned_employee_id, priority, organization_id, created_at, rule_type, apartment_code
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys:** none declared
- **date coverage:** created_at 2026-03-20..2026-03-20 (1 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `ticket_cost_estimates`

- **object type:** table  |  **size:** 72 kB
- **counted rows (M.006):** 28
- **exported rows:** 28  (matches)
- **export file:** manifest key `T.ticket_cost_estimates`
- **columns (21):** id, ticket_id, organization_id, item_name, cost_type, quantity, unit_price, total, status, submitted_by, approved_by, decline_reason, approved_at, created_at, item_type, price, updated_at, is_auto_approved, auto_approval_reason, repeat_job_alert, repeat_job_previous_ticket_id
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** organization_id -> organizations.id [NO ACTION]; ticket_id -> maintenance_tickets.id [CASCADE]
- **date coverage:** approved_at 2026-04-30..2026-07-17 (4 mo); created_at 2026-04-16..2026-07-17 (4 mo); updated_at 2026-04-16..2026-07-17 (4 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `ticket_cost_estimates_dedupe_backup_20260715`

- **object type:** table  |  **size:** 16 kB
- **counted rows (M.006):** 12
- **exported rows:** 12  (matches)
- **export file:** manifest key `T.ticket_cost_estimates_dedupe_backup_20260715`
- **columns (21):** id, ticket_id, organization_id, item_name, cost_type, quantity, unit_price, total, status, submitted_by, approved_by, decline_reason, approved_at, created_at, item_type, price, updated_at, is_auto_approved, auto_approval_reason, repeat_job_alert, repeat_job_previous_ticket_id
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys:** none declared
- **date coverage:** approved_at 2026-04-30..2026-06-25 (2 mo); created_at 2026-04-30..2026-06-25 (2 mo); updated_at 2026-04-30..2026-06-25 (2 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `ticket_logs`

- **object type:** table  |  **size:** 3184 kB
- **counted rows (M.006):** 8239
- **exported rows:** 8240  **(delta +1 vs M.006)**
- **export file:** manifest key `T.ticket_logs`
- **export note:** base table; notes EXCLUDED; +1 row vs M.006 (live write)
- **columns (9):** id, ticket_id, action, old_status, new_status, created_by, notes, created_at, organization_id
- **organization_id:** present; distinct_orgs=1, null_org_rows=65 **<- NULL org rows present**
- **foreign keys (1):** ticket_id -> maintenance_tickets.id [CASCADE]
- **date coverage:** created_at 2026-03-31..2026-08-29 (6 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `ticket_number_counters`

- **object type:** table  |  **size:** 56 kB
- **counted rows (M.006):** 5
- **exported rows:** 5  (matches)
- **export file:** manifest key `T.ticket_number_counters`
- **columns (6):** organization_id, property_id, yy, mm, last_seq, updated_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** organization_id -> organizations.id [CASCADE]; property_id -> properties.id [CASCADE]
- **date coverage:** updated_at 2026-04-30..2026-08-29 (5 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `ticket_purchases`

- **object type:** table  |  **size:** 32 kB
- **counted rows (M.006):** 4
- **exported rows:** 4  (matches)
- **export file:** manifest key `T.ticket_purchases`
- **columns (15):** id, ticket_id, cost_estimate_id, organization_id, quantity, estimated_cost, actual_cost, vendor_id, vendor_name_manual, invoice_url, purchased_by, purchase_date, created_at, updated_at, item_name
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (6):** cost_estimate_id -> ticket_cost_estimates.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]; ticket_id -> maintenance_tickets.id [CASCADE]; ticket_id -> maintenance_tickets.id [CASCADE]; vendor_id -> vendors.id [SET NULL]; vendor_id -> vendors.id [NO ACTION]
- **date coverage:** created_at 2026-04-30..2026-06-25 (3 mo); purchase_date 2026-04-30..2026-06-25 (3 mo); updated_at 2026-04-30..2026-06-25 (3 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `ticket_resolutions`

- **object type:** table  |  **size:** 312 kB
- **counted rows (M.006):** 466
- **exported rows:** 466  (matches)
- **export file:** manifest key `T.ticket_resolutions`
- **columns (24):** id, ticket_id, organization_id, resolution_type, service_type, vendor_id, vendor_name_manual, items_used, total_parts_cost, total_labour_cost, total_cost, closure_summary, resolved_at, resolved_by, created_at, bank_account_id, payment_date, payment_reference_no, proof_of_purchase_url, proof_of_payment_url, actual_items_used, actual_total_cost, diagnostic_estimated_cost, updated_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (3):** bank_account_id -> organization_bank_accounts.id [SET NULL]; ticket_id -> maintenance_tickets.id [CASCADE]; vendor_id -> vendors.id [NO ACTION]
- **date coverage:** created_at 2026-04-17..2026-08-24 (5 mo); payment_date 2026-04-23..2026-08-24 (4 mo); resolved_at 2026-04-17..2026-08-24 (5 mo); updated_at 2026-04-28..2026-08-27 (5 mo)
- **sensitivity:** EXCLUDED: proof_of_payment_url, proof_of_purchase_url | HASHED: bank_account_id
- **analytics suitability:** Supporting / operational.

### `tickets`

- **object type:** table  |  **size:** 48 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (18):** id, ticket_number, issue_type_id, description, status, priority, approval_status, assigned_employee_id, created_by, tenant_id, property_id, apartment_id, bed_id, organization_id, total_cost, sla_deadline, created_at, updated_at
- **organization_id:** present; distinct_orgs=0, null_org_rows=0
- **foreign keys:** none declared
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `upi_tenant_mappings`

- **object type:** table  |  **size:** 40 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (11):** id, organization_id, tenant_id, upi_id, normalized_upi_id, bank_transaction_ref, normalized_transaction_ref, confidence, match_source, last_seen_at, created_at
- **organization_id:** present; distinct_orgs=0, null_org_rows=0
- **foreign keys:** none declared
- **date coverage:** no dated column profiled
- **sensitivity:** HASHED: bank_transaction_ref, normalized_transaction_ref, normalized_upi_id, upi_id
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `user_roles`

- **object type:** table  |  **size:** 72 kB
- **counted rows (M.006):** 209
- **exported rows:** 210  **(delta +1 vs M.006)**
- **export file:** manifest key `T.user_roles`
- **export note:** base table, full column set; +1 row vs M.006 (live write)
- **columns (3):** id, user_id, role
- **organization_id:** absent
- **foreign keys (1):** user_id -> users.id [CASCADE]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

### `users`

- **object type:** table  |  **size:** 40 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (16):** id, first_name, last_name, name, email, email_verified_at, phone, phone_verified_at, is_anonymous, role, must_set_password, password_set_at, active_session_id, last_login_at, reports_to, created_at
- **organization_id:** absent
- **foreign keys (1):** reports_to -> users.id [NO ACTION]
- **date coverage:** no dated column profiled
- **sensitivity:** EXCLUDED: active_session_id, must_set_password, password_set_at | HASHED: email, email_verified_at, phone, phone_verified_at | kept-but-flagged: first_name, last_name
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `vendor_remarks`

- **object type:** table  |  **size:** 48 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (9):** id, organization_id, vendor_id, remark_type, title, description, severity, created_by, created_at
- **organization_id:** present; distinct_orgs=0, null_org_rows=0
- **foreign keys (1):** vendor_id -> vendors.id [CASCADE]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `vendors`

- **object type:** table  |  **size:** 72 kB
- **counted rows (M.006):** 40
- **exported rows:** 40  (matches)
- **export file:** manifest key `T.vendors`
- **columns (17):** id, organization_id, vendor_name, contact_person, phone, email, address, created_at, gst_number, pan_number, bank_name, bank_account_number, bank_ifsc, id_proof_url, status, notes, vendor_rating
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (1):** organization_id -> organizations.id [NO ACTION]
- **date coverage:** created_at 2026-03-17..2026-04-11 (2 mo)
- **sensitivity:** EXCLUDED: id_proof_url | HASHED: bank_account_number, bank_ifsc, email, gst_number, pan_number, phone
- **analytics suitability:** Supporting / operational.

### `whatsapp_conversations`

- **object type:** table  |  **size:** 40 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (13):** id, organization_id, tenant_id, provider, phone_e164, status, pending_action, last_user_message, last_assistant_message, last_event_id, expires_at, created_at, updated_at
- **organization_id:** present; distinct_orgs=0, null_org_rows=0
- **foreign keys (3):** last_event_id -> whatsapp_events.id [NO ACTION]; organization_id -> organizations.id [NO ACTION]; tenant_id -> tenants.id [NO ACTION]
- **date coverage:** no dated column profiled
- **sensitivity:** HASHED: phone_e164
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `whatsapp_dedup`

- **object type:** table  |  **size:** 72 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (5):** id, provider, dedup_key, event_id, created_at
- **organization_id:** absent
- **foreign keys (1):** event_id -> whatsapp_events.id [CASCADE]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `whatsapp_events`

- **object type:** table  |  **size:** 3152 kB
- **counted rows (M.006):** 1943
- **exported rows:** 1943  (matches)
- **export file:** manifest key `T.whatsapp_events`
- **columns (23):** id, organization_id, tenant_id, provider, direction, event_type, external_message_id, external_conversation_id, from_phone, to_phone, message_type, message_text, language, transcript, transcript_en, raw_payload, normalized_payload, processing_status, correlation_id, processed_at, error_message, created_at, updated_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=600 **<- NULL org rows present**
- **foreign keys (2):** organization_id -> organizations.id [NO ACTION]; tenant_id -> tenants.id [NO ACTION]
- **date coverage:** created_at 2026-05-16..2026-08-29 (4 mo); processed_at 2026-05-29..2026-06-10 (2 mo); updated_at 2026-05-16..2026-08-29 (4 mo)
- **sensitivity:** HASHED: from_phone, to_phone
- **analytics suitability:** Supporting / operational.

### `whatsapp_failures`

- **object type:** table  |  **size:** 32 kB
- **counted rows (M.006):** 0
- **exported rows:** NOT EXPORTED - table is **empty** (0 rows). Recorded as empty, not missing.
- **columns (9):** id, event_id, stage, attempt_count, next_retry_at, last_error, dead_letter, created_at, updated_at
- **organization_id:** absent
- **foreign keys (1):** event_id -> whatsapp_events.id [CASCADE]
- **date coverage:** no dated column profiled
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** **No** - empty table. Confirms feature unused / superseded.

### `whatsapp_payment_submissions`

- **object type:** table  |  **size:** 504 kB
- **counted rows (M.006):** 387
- **exported rows:** 387  (matches)
- **export file:** manifest key `T.whatsapp_payment_submissions`
- **columns (31):** id, organization_id, tenant_id, from_phone, whatsapp_event_id, image_url, image_original_url, ocr_amount, ocr_payment_mode, ocr_transaction_reference, ocr_receiving_bank, ocr_raw, ocr_confidence, status, receipt_id, verified_by, verified_at, rejection_reason, created_at, updated_at, matched_invoice_id, match_confidence, ocr_sender_bank, ocr_sender_account_holder, ocr_receiver_upi_id, ocr_receiver_account_last4, auto_accept_skip_reason, auto_accept_decision, ocr_sender_upi_id, ocr_receiving_upi_id, ocr_payment_date
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (6):** matched_invoice_id -> invoices.id [SET NULL]; organization_id -> organizations.id [CASCADE]; receipt_id -> receipts.id [SET NULL]; tenant_id -> tenants.id [SET NULL]; verified_by -> users.id [SET NULL]; whatsapp_event_id -> whatsapp_events.id [SET NULL]
- **date coverage:** created_at 2026-06-01..2026-08-27 (3 mo); ocr_payment_date 2023-07-02..2026-08-16 (5 mo); updated_at 2026-06-01..2026-08-27 (3 mo); verified_at 2026-06-01..2026-08-27 (3 mo)
- **sensitivity:** HASHED: from_phone, ocr_receiver_upi_id, ocr_receiving_upi_id, ocr_sender_upi_id
- **analytics suitability:** Supporting / operational.

### `whatsapp_send_deliveries`

- **object type:** table  |  **size:** 2464 kB
- **counted rows (M.006):** 2422
- **exported rows:** 2422  (matches)
- **export file:** manifest key `T.whatsapp_send_deliveries`
- **columns (14):** id, organization_id, job_id, delivery_kind, reference_id, tenant_id, tenant_name, label, payload, status, error_message, phone_masked, created_at, sent_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** job_id -> whatsapp_send_jobs.id [CASCADE]; organization_id -> organizations.id [CASCADE]
- **date coverage:** created_at 2026-05-31..2026-08-17 (4 mo); sent_at 2026-05-31..2026-08-17 (4 mo)
- **sensitivity:** HASHED: phone_masked
- **analytics suitability:** Supporting / operational.

### `whatsapp_send_jobs`

- **object type:** table  |  **size:** 672 kB
- **counted rows (M.006):** 395
- **exported rows:** 395  (matches)
- **export file:** manifest key `T.whatsapp_send_jobs`
- **columns (15):** id, organization_id, created_by, job_type, status, total_count, sent_count, failed_count, error_message, error_details, payload, label, dismissed_at, created_at, updated_at
- **organization_id:** present; distinct_orgs=1, null_org_rows=0
- **foreign keys (2):** created_by -> users.id [SET NULL]; organization_id -> organizations.id [CASCADE]
- **date coverage:** created_at 2026-05-31..2026-08-17 (4 mo); dismissed_at 2026-06-08..2026-08-05 (3 mo); updated_at 2026-05-31..2026-08-17 (4 mo)
- **sensitivity:** no sensitive columns classified
- **analytics suitability:** Supporting / operational.

---

## A.2 Public views (54)

28 business views were exported (manifest keys `F.001`-`F.028`; `F.026` is a byte-identical re-export of `F.025`, so **27 distinct** business views carry data). 8 further diagnostic views were exported under `H.*` keys. 19 views were not exported - reasons below.

### `maintenance_item_low_stock`

- **object type:** view  |  **columns:** 5  |  **definition length:** 201 chars (SQL in M.016)
- **columns:** organization_id, maintenance_item_id, current_stock, minimum_stock_level, last_purchase_cost
- **exported:** **AMBIGUOUS.** Its column list is identical to `maintenance_item_stock_summary`. The 93-row export (F.025/F.026) equals the full `maintenance_items` count (93), so it is attributed to `maintenance_item_stock_summary`. Whether `maintenance_item_low_stock` was separately exported is **not determinable from exported evidence**.
- **analytics suitability:** Not usable offline - no data exported.

### `maintenance_item_stock_summary`

- **object type:** view  |  **columns:** 5  |  **definition length:** 478 chars (SQL in M.016)
- **columns:** organization_id, maintenance_item_id, current_stock, minimum_stock_level, last_purchase_cost
- **exported:** yes - key(s) `F.025, F.026`, rows=93
- **note:** EXACT DUPLICATE of F.025 [ambiguous: public.maintenance_item_stock_summary/public.maintenance_item_low_stock]
- **note:** business view export [ambiguous: public.maintenance_item_stock_summary/public.maintenance_item_low_stock]
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_account_balances`

- **object type:** view  |  **columns:** 23  |  **definition length:** 1042 chars (SQL in M.016)
- **columns:** organization_id, entry_date, period, journal_entry_id, source_table, source_id, is_reversal_of, account_id, account_code, account_name, account_type, normal_balance, parent_code, parent_name, party_kind, party_id, allotment_id, property_id, apartment_id, bed_id, debit, credit, signed_amount
- **exported:** yes - key(s) `F.021`, rows=32040
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_account_rollup`

- **object type:** view  |  **columns:** 10  |  **definition length:** 1599 chars (SQL in M.016)
- **columns:** organization_id, account_id, code, name, account_type, normal_balance, parent_id, total_debit_rollup, total_credit_rollup, balance_rollup
- **exported:** yes - key(s) `F.014`, rows=57
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_active_tenants`

- **object type:** view  |  **columns:** 5  |  **definition length:** 417 chars (SQL in M.016)
- **columns:** organization_id, property_id, active_tenants, booked_tenants, total_tenants_ever
- **exported:** yes - key(s) `F.022`, rows=1
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_advance_balances`

- **object type:** view  |  **columns:** 5  |  **definition length:** 541 chars (SQL in M.016)
- **columns:** organization_id, tenant_id, allotment_id, deposit_held, booking_advance
- **exported:** yes - key(s) `F.010`, rows=509
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_asset_payment_status`

- **object type:** view  |  **columns:** 14  |  **definition length:** 1424 chars (SQL in M.016)
- **columns:** asset_id, organization_id, asset_code, invoice_number, invoice_date, purchase_date, purchase_price, supplier_id, vendor_name, total_paid, balance_due, payment_count, last_payment_date, status
- **exported:** yes - key(s) `F.024`, rows=308
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_bed_expense_breakdown`

- **object type:** view  |  **columns:** 8  |  **definition length:** 519 chars (SQL in M.016)
- **columns:** organization_id, bed_id, apartment_id, property_id, month, category_code, category_name, amount
- **exported:** yes - key(s) `F.020`, rows=385
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_deposit_ledger_anomalies`

- **object type:** view  |  **columns:** 6  |  **definition length:** 3633 chars (SQL in M.016)
- **columns:** organization_id, tenant_id, allotment_id, settlement_id, anomaly, details
- **exported:** no
- **analytics suitability:** Not usable offline - no data exported.

### `v_diag_allotment_balance_drift`

- **object type:** view  |  **columns:** 5  |  **definition length:** 1043 chars (SQL in M.016)
- **columns:** allotment_id, organization_id, stored_balance, computed_balance, drift
- **exported:** no
- **analytics suitability:** Not usable offline - no data exported.

### `v_diag_deposit_phantom`

- **object type:** view  |  **columns:** 7  |  **definition length:** 514 chars (SQL in M.016)
- **columns:** organization_id, allotment_id, tenant_id, deposit_paid, staying_status, actual_exit_date, note
- **exported:** no
- **analytics suitability:** Not usable offline - no data exported.

### `v_diag_invoice_drift`

- **object type:** view  |  **columns:** 9  |  **definition length:** 372 chars (SQL in M.016)
- **columns:** organization_id, invoice_id, invoice_number, billing_month, total_amount, amount_paid, balance, drift, status
- **exported:** no
- **analytics suitability:** Not usable offline - no data exported.

### `v_diag_orphan_receipts`

- **object type:** view  |  **columns:** 7  |  **definition length:** 223 chars (SQL in M.016)
- **columns:** organization_id, receipt_id, tenant_id, payment_date, amount_paid, receipt_type, receipt_number
- **exported:** no - **view is EMPTY (0 rows)**, recorded in H.032 `diagnostic_view_rowcounts`. Absence is explained, not a gap.
- **analytics suitability:** Not usable offline - no data exported.

### `v_diag_owner_rent_missing_from_profit`

- **object type:** view  |  **columns:** 4  |  **definition length:** 470 chars (SQL in M.016)
- **columns:** organization_id, month, owner_rent_paid_or_accrued, note
- **exported:** yes - key(s) `F.028`, rows=46
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_exit_reconciliation_worklist`

- **object type:** view  |  **columns:** 17  |  **definition length:** 1830 chars (SQL in M.016)
- **columns:** organization_id, tenant_id, allotment_id, property_id, apartment_id, bed_id, tenant_name, property_name, apartment_code, bed_code, bed_label, actual_exit_date, dues_now, deposit_held, eb_already, exit_charge_already, settlement_status
- **exported:** yes - key(s) `F.027`, rows=45
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_expense_composition`

- **object type:** view  |  **columns:** 10  |  **definition length:** 1539 chars (SQL in M.016)
- **columns:** organization_id, property_id, month, category_code, category_name, account_code, account_name, amount, pct_of_category, pct_of_total
- **exported:** yes - key(s) `F.019`, rows=138
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_expenses_by_period`

- **object type:** view  |  **columns:** 6  |  **definition length:** 411 chars (SQL in M.016)
- **columns:** organization_id, property_id, month, account_code, account_name, expense
- **exported:** yes - key(s) `F.004`, rows=138
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_export_apartments`

- **object type:** view  |  **columns:** 20  |  **definition length:** 567 chars (SQL in M.016)
- **columns:** id, organization_id, property_id, property_name, apartment_code, apartment_type, floor_number, size_sqft, gender_allowed, status, owner_id, star_rating, eb_meter_number, eb_consumer_number, created_at, updated_at, created_by, created_by_name, updated_by, updated_by_name
- **exported:** no - PII-safe export wrapper. The underlying base table was exported directly instead (with the same PII exclusions applied), so this wrapper is redundant.
- **analytics suitability:** Not usable offline - no data exported.

### `v_export_assets`

- **object type:** view  |  **columns:** 28  |  **definition length:** 872 chars (SQL in M.016)
- **columns:** id, organization_id, property_id, property_name, apartment_id, apartment_code, bed_id, asset_type_id, asset_type_name, asset_code, brand, model, serial_number, purchase_date, purchase_price, warranty_expiry, warranty_months, status, condition, vendor_name_manual, invoice_number, invoice_date, created_at, updated_at, created_by, created_by_name, updated_by, updated_by_name
- **exported:** no - PII-safe export wrapper. The underlying base table was exported directly instead (with the same PII exclusions applied), so this wrapper is redundant.
- **analytics suitability:** Not usable offline - no data exported.

### `v_export_audit_logs`

- **object type:** view  |  **columns:** 16  |  **definition length:** 441 chars (SQL in M.016)
- **columns:** id, organization_id, table_name, record_id, action, created_at, created_by, created_by_name, updated_at, updated_by, updated_by_name, old_value, new_value, changes, status, tenant_id
- **exported:** no - PII-safe export wrapper. The underlying base table was exported directly instead (with the same PII exclusions applied), so this wrapper is redundant.
- **analytics suitability:** Not usable offline - no data exported.

### `v_export_beds`

- **object type:** view  |  **columns:** 17  |  **definition length:** 587 chars (SQL in M.016)
- **columns:** id, organization_id, property_id, property_name, apartment_id, apartment_code, bed_code, bed_type, toilet_type, status, bed_lifecycle_status, created_at, updated_at, created_by, created_by_name, updated_by, updated_by_name
- **exported:** no - PII-safe export wrapper. The underlying base table was exported directly instead (with the same PII exclusions applied), so this wrapper is redundant.
- **analytics suitability:** Not usable offline - no data exported.

### `v_export_deposit_settlements`

- **object type:** view  |  **columns:** 23  |  **definition length:** 639 chars (SQL in M.016)
- **columns:** id, organization_id, tenant_id, tenant_name, allotment_id, settlement_date, deposit_amount, pending_rent, pending_eb, pending_late_fees, damages, other_deductions, total_deductions, refund_amount, status, notes, is_deleted, created_at, updated_at, created_by, created_by_name, updated_by, updated_by_name
- **exported:** no - PII-safe export wrapper. The underlying base table was exported directly instead (with the same PII exclusions applied), so this wrapper is redundant.
- **analytics suitability:** Not usable offline - no data exported.

### `v_export_electricity_readings`

- **object type:** view  |  **columns:** 24  |  **definition length:** 962 chars (SQL in M.016)
- **columns:** id, organization_id, property_id, property_name, apartment_id, apartment_code, billing_month, reading_start, reading_end, units_consumed, unit_cost, total_amount, meter_photo_url, is_locked, locked_by, locked_by_name, created_at, updated_at, created_by, created_by_name, updated_by, updated_by_name, status, tenant_id
- **exported:** no - PII-safe export wrapper. The underlying base table was exported directly instead (with the same PII exclusions applied), so this wrapper is redundant.
- **analytics suitability:** Not usable offline - no data exported.

### `v_export_expenses`

- **object type:** view  |  **columns:** 29  |  **definition length:** 1037 chars (SQL in M.016)
- **columns:** id, organization_id, property_id, property_name, apartment_id, apartment_code, bed_id, bed_code, category_id, category_label, subcategory_id, subcategory_label, vendor_id, vendor_name, amount, expense_date, billing_month, description, data_source, receipt_url, related_asset_id, ticket_resolution_id, created_at, updated_at, created_by, created_by_name, updated_by, updated_by_name, status
- **exported:** no - PII-safe export wrapper. The underlying base table was exported directly instead (with the same PII exclusions applied), so this wrapper is redundant.
- **analytics suitability:** Not usable offline - no data exported.

### `v_export_invoices`

- **object type:** view  |  **columns:** 35  |  **definition length:** 985 chars (SQL in M.016)
- **columns:** id, organization_id, tenant_id, tenant_name, allotment_id, property_id, property_name, apartment_id, apartment_code, bed_id, bed_code, invoice_number, invoice_type, billing_month, invoice_date, due_date, rent_amount, electricity_amount, estimated_eb, late_fee, other_charges, total_amount, amount_paid, balance, status, reference_type, reference_id, locked, is_deleted, created_at, updated_at, created_by, created_by_name, updated_by, updated_by_name
- **exported:** no - PII-safe export wrapper. The underlying base table was exported directly instead (with the same PII exclusions applied), so this wrapper is redundant.
- **analytics suitability:** Not usable offline - no data exported.

### `v_export_journal_entries`

- **object type:** view  |  **columns:** 19  |  **definition length:** 511 chars (SQL in M.016)
- **columns:** id, organization_id, entry_date, period, source_table, source_id, description, is_reversal_of, posted_at, posted_by, posted_by_name, metadata, created_at, updated_at, created_by, created_by_name, updated_by, updated_by_name, status
- **exported:** no - PII-safe export wrapper. The underlying base table was exported directly instead (with the same PII exclusions applied), so this wrapper is redundant.
- **analytics suitability:** Not usable offline - no data exported.

### `v_export_journal_lines`

- **object type:** view  |  **columns:** 30  |  **definition length:** 981 chars (SQL in M.016)
- **columns:** id, organization_id, journal_entry_id, entry_date, period, source_table, source_id, line_no, account_id, account_code, account_name, account_type, debit, credit, memo, party_kind, party_id, allotment_id, property_id, property_name, apartment_id, bed_id, created_at, updated_at, created_by, created_by_name, updated_by, updated_by_name, status, tenant_id
- **exported:** no - PII-safe export wrapper. The underlying base table was exported directly instead (with the same PII exclusions applied), so this wrapper is redundant.
- **analytics suitability:** Not usable offline - no data exported.

### `v_export_maintenance_tickets`

- **object type:** view  |  **columns:** 32  |  **definition length:** 1101 chars (SQL in M.016)
- **columns:** id, organization_id, ticket_number, status, priority, description, issue_type_id, issue_type_name, issue_sub_type_id, property_id, property_name, apartment_id, apartment_code, bed_id, bed_code, tenant_id, tenant_name, tenant_phone, assigned_to, assigned_to_name, asset_id, sla_deadline, resolved_at, closed_at, tenant_approved, tenant_rejection_reason, created_at, updated_at, created_by, created_by_name, updated_by, updated_by_name
- **exported:** no - PII-safe export wrapper. The underlying base table was exported directly instead (with the same PII exclusions applied), so this wrapper is redundant.
- **analytics suitability:** Not usable offline - no data exported.

### `v_export_properties`

- **object type:** view  |  **columns:** 18  |  **definition length:** 407 chars (SQL in M.016)
- **columns:** id, organization_id, property_name, property_code, status, address, city, state, pincode, gps_latitude, gps_longitude, start_date, created_at, updated_at, created_by, created_by_name, updated_by, updated_by_name
- **exported:** no - PII-safe export wrapper. The underlying base table was exported directly instead (with the same PII exclusions applied), so this wrapper is redundant.
- **analytics suitability:** Not usable offline - no data exported.

### `v_export_receipt_allocations`

- **object type:** view  |  **columns:** 18  |  **definition length:** 691 chars (SQL in M.016)
- **columns:** id, organization_id, receipt_id, receipt_number, invoice_id, invoice_number, amount, created_at, updated_at, created_by, created_by_name, updated_by, updated_by_name, tenant_id, tenant_name, adjustment_id, notes, status
- **exported:** no - PII-safe export wrapper. The underlying base table was exported directly instead (with the same PII exclusions applied), so this wrapper is redundant.
- **analytics suitability:** Not usable offline - no data exported.

### `v_export_receipts`

- **object type:** view  |  **columns:** 25  |  **definition length:** 812 chars (SQL in M.016)
- **columns:** id, organization_id, tenant_id, tenant_name, allotment_id, receipt_number, receipt_type, amount_paid, base_amount, processing_fee, payment_date, payment_mode, reference_number, bank_account_id, bank_account_name, is_locked, locked_by, locked_by_name, is_deleted, created_at, updated_at, created_by, created_by_name, updated_by, updated_by_name
- **exported:** no - PII-safe export wrapper. The underlying base table was exported directly instead (with the same PII exclusions applied), so this wrapper is redundant.
- **analytics suitability:** Not usable offline - no data exported.

### `v_export_tenant_adjustments`

- **object type:** view  |  **columns:** 30  |  **definition length:** 1006 chars (SQL in M.016)
- **columns:** id, organization_id, tenant_id, tenant_name, allotment_id, property_id, property_name, apartment_id, apartment_code, bed_id, bed_code, adjustment_type, category, amount, adjustment_date, billing_month, reason, reference_type, reference_id, reference_number, is_locked, locked_by, locked_by_name, is_deleted, created_at, created_by, created_by_name, updated_at, updated_by, updated_by_name
- **exported:** no - PII-safe export wrapper. The underlying base table was exported directly instead (with the same PII exclusions applied), so this wrapper is redundant.
- **analytics suitability:** Not usable offline - no data exported.

### `v_export_tenant_allotments`

- **object type:** view  |  **columns:** 36  |  **definition length:** 1117 chars (SQL in M.016)
- **columns:** id, organization_id, tenant_id, tenant_name, tenant_phone, property_id, property_name, apartment_id, apartment_code, bed_id, bed_code, status, booking_date, onboarding_date, notice_date, estimated_exit_date, actual_exit_date, monthly_rental, deposit_paid, onboarding_charges, processing_fee, discount, premium, prorated_rent, payment_status, paid_amount, total_due, balance_due, expected_stay_days, expected_payment_date, created_at, updated_at, created_by, created_by_name, updated_by, updated_by_name
- **exported:** no - PII-safe export wrapper. The underlying base table was exported directly instead (with the same PII exclusions applied), so this wrapper is redundant.
- **analytics suitability:** Not usable offline - no data exported.

### `v_export_tenants`

- **object type:** view  |  **columns:** 29  |  **definition length:** 676 chars (SQL in M.016)
- **columns:** id, organization_id, property_id, property_name, user_id, first_name, last_name, full_name, phone, email, gender, date_of_birth, date_of_joining, staying_status, profession, company_name, city, state, pincode, kyc_completed, tenant_rating, pan_number, gst_number, created_at, updated_at, created_by, created_by_name, updated_by, updated_by_name
- **exported:** no - PII-safe export wrapper. The underlying base table was exported directly instead (with the same PII exclusions applied), so this wrapper is redundant.
- **analytics suitability:** Not usable offline - no data exported.

### `v_invoice_settlement_status`

- **object type:** view  |  **columns:** 10  |  **definition length:** 2981 chars (SQL in M.016)
- **columns:** organization_id, tenant_id, allotment_id, source_table, invoice_id, invoice_date, invoice_amount, amount_settled, amount_outstanding, settlement_status
- **exported:** yes - key(s) `F.009`, rows=5379
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_je_amount_reconciliation`

- **object type:** view  |  **columns:** 5  |  **definition length:** 6346 chars (SQL in M.016)
- **columns:** source_table, legacy_amount, je_net_amount, diff, verdict
- **exported:** no
- **analytics suitability:** Not usable offline - no data exported.

### `v_je_intentional_skips`

- **object type:** view  |  **columns:** 6  |  **definition length:** 1390 chars (SQL in M.016)
- **columns:** kind, source_id, reference, dt, amount, status
- **exported:** no
- **analytics suitability:** Not usable offline - no data exported.

### `v_je_source_counts`

- **object type:** view  |  **columns:** 7  |  **definition length:** 2841 chars (SQL in M.016)
- **columns:** source_table, legacy_live, legacy_total, je_forward, je_reversal, je_distinct_sources, gap_live_minus_je
- **exported:** no
- **analytics suitability:** Not usable offline - no data exported.

### `v_je_stub_pollution`

- **object type:** view  |  **columns:** 5  |  **definition length:** 659 chars (SQL in M.016)
- **columns:** source_table, empty_forward_je, empty_reversal_je, posted_je, total_je
- **exported:** no
- **analytics suitability:** Not usable offline - no data exported.

### `v_maintenance_by_issue_type`

- **object type:** view  |  **columns:** 9  |  **definition length:** 1031 chars (SQL in M.016)
- **columns:** organization_id, property_id, month, issue_type_id, issue_type_name, resolved_tickets, total_cost, avg_cost_per_ticket, pct_of_maintenance
- **exported:** yes - key(s) `F.016`, rows=9
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_maintenance_metrics`

- **object type:** view  |  **columns:** 7  |  **definition length:** 680 chars (SQL in M.016)
- **columns:** organization_id, property_id, month, tickets, closed, open, cost
- **exported:** yes - key(s) `F.015`, rows=20
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_occupancy`

- **object type:** view  |  **columns:** 8  |  **definition length:** 1482 chars (SQL in M.016)
- **columns:** organization_id, property_id, total_beds, occupied, on_notice, booked, vacant, occupancy_pct
- **exported:** yes - key(s) `F.005`, rows=1
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_org_cash_balance`

- **object type:** view  |  **columns:** 2  |  **definition length:** 181 chars (SQL in M.016)
- **columns:** organization_id, cash_on_hand
- **exported:** yes - key(s) `F.011`, rows=1
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_outstanding_receivables`

- **object type:** view  |  **columns:** 6  |  **definition length:** 412 chars (SQL in M.016)
- **columns:** organization_id, tenant_id, allotment_id, outstanding, last_charge_date, last_payment_date
- **exported:** yes - key(s) `F.006`, rows=626
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_pnl`

- **object type:** view  |  **columns:** 6  |  **definition length:** 937 chars (SQL in M.016)
- **columns:** organization_id, property_id, month, revenue, expenses, net_profit
- **exported:** yes - key(s) `F.001`, rows=57
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_pnl_by_category`

- **object type:** view  |  **columns:** 22  |  **definition length:** 3949 chars (SQL in M.016)
- **columns:** organization_id, property_id, month, revenue, rental_income, electricity_income, guest_stay_income, onboarding_income, late_fees_income, exit_charges_income, total_expenses, owner_rent, maintenance, housekeeping, utilities, property_ops, administrative, salaries, marketing, other_expenses, net_profit, electricity
- **exported:** yes - key(s) `F.002`, rows=57
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_property_expense_share`

- **object type:** view  |  **columns:** 5  |  **definition length:** 836 chars (SQL in M.016)
- **columns:** organization_id, month, property_id, expenses, pct_of_org_expenses
- **exported:** yes - key(s) `F.023`, rows=46
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_revenue_by_period`

- **object type:** view  |  **columns:** 6  |  **definition length:** 410 chars (SQL in M.016)
- **columns:** organization_id, property_id, month, account_code, account_name, revenue
- **exported:** yes - key(s) `F.003`, rows=224
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_tenant_aging`

- **object type:** view  |  **columns:** 8  |  **definition length:** 1285 chars (SQL in M.016)
- **columns:** organization_id, tenant_id, allotment_id, bucket_0_30, bucket_31_60, bucket_61_90, bucket_90_plus, total
- **exported:** yes - key(s) `F.008`, rows=644
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_tenant_current_dues`

- **object type:** view  |  **columns:** 11  |  **definition length:** 1367 chars (SQL in M.016)
- **columns:** organization_id, tenant_id, allotment_id, ar_balance, deposit_held, booking_advance, net_dues, last_payment_date, last_charge_date, charge_count, payment_count
- **exported:** yes - key(s) `F.007`, rows=645
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_tenant_ledger`

- **object type:** view  |  **columns:** 19  |  **definition length:** 928 chars (SQL in M.016)
- **columns:** organization_id, tenant_id, allotment_id, entry_date, posted_at, journal_entry_id, is_reversal_of, source_table, source_id, description, account_code, account_name, debit, credit, running_balance, memo, property_id, apartment_id, bed_id
- **exported:** yes - key(s) `F.018`, rows=14200
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_tenant_lifecycle_events`

- **object type:** view  |  **columns:** 9  |  **definition length:** 615 chars (SQL in M.016)
- **columns:** organization_id, property_id, apartment_id, bed_id, tenant_id, allotment_id, event_date, event, staying_status
- **exported:** yes - key(s) `F.017`, rows=2204
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_trial_balance`

- **object type:** view  |  **columns:** 8  |  **definition length:** 315 chars (SQL in M.016)
- **columns:** organization_id, account_code, account_name, account_type, normal_balance, total_debit, total_credit, balance
- **exported:** yes - key(s) `F.012`, rows=24
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

### `v_trial_balance_detailed`

- **object type:** view  |  **columns:** 15  |  **definition length:** 1924 chars (SQL in M.016)
- **columns:** organization_id, account_id, code, name, account_type, normal_balance, parent_id, depth, root_code, root_name, total_debit, total_credit, net_debit, balance, is_active
- **exported:** yes - key(s) `F.013`, rows=57
- **note:** business view export
- **analytics suitability:** **Yes - exported business view, usable as a reconstruction target.**

---

## A.3 market schema (17 tables) - IN_SCOPE but NOT exported

M.000 `schema_scope` marks `market` as **IN_SCOPE** alongside `public`. No market table data was exported. Only row counts survive, and only for 7 of the 17 tables (H.037).

| table | counted rows (M.006) | in H.037 | data exported |
|---|---|---|---|
| `amenities_master` | 15 | no | no |
| `amenity_embeddings` | 0 | no | no |
| `competitor_intelligence` | 133 | no | no |
| `competitor_pricing_snapshots` | 0 | yes | no |
| `competitor_pricing_snapshots_2026_05` | 0 | no | no |
| `competitor_pricing_snapshots_2026_06` | 0 | no | no |
| `competitor_pricing_snapshots_2026_07` | 0 | no | no |
| `competitor_pricing_snapshots_2026_08` | 0 | no | no |
| `competitor_properties` | 257 | yes | no |
| `competitor_reviews` | 0 | yes | no |
| `competitor_room_types` | 1 | yes | no |
| `localities` | 6 | yes | no |
| `locality_market_metrics` | 0 | yes | no |
| `org_tracked_localities` | 5 | yes | no |
| `property_embeddings` | 0 | no | no |
| `review_embeddings` | 0 | no | no |
| `scrape_sources` | 4 | no | no |

Market tables holding data: `amenities_master` (15), `competitor_intelligence` (133), `competitor_properties` (257), `competitor_room_types` (1), `localities` (6), `org_tracked_localities` (5), `scrape_sources` (4) = **421 rows unavailable offline**. None of the 13 required metric areas depends on `market`, so this gap does not block reconstruction - but it is a real scope shortfall against M.000.
