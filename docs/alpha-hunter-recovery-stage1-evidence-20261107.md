# Alpha Hunter — Database Recovery V1.0 / Stage 1 Evidence Ledger

**Date:** 2026-11-07 (UTC)
**Priority:** P0
**Status:** PRODUCTION REPAIR REQUIRED — NO-GO
**Source:** Read-only connected Supabase SQL/log queries, GitHub PR #445, Render service metadata/logs.
**Release branch:** `fix/supabase-write-timeout-qa`; draft PR #445; unmerged at audit.
**Safety:** No production SQL writes, DDL, deploy, scanner change, trading permissions or paid infrastructure authorised by this evidence collection.

## 1. Latest read-only core-persistence acceptance
Method: `ops/sql/readonly_core_scan_persistence_gate_v01.sql`; 12 most recent parent scans inspected from `public.alpha_hunter_snapshots`, with indexed per-run counts for symbols, signals, features, readiness and orphan identity checks.

| Scan collected UTC | Declared symbols | Symbol / signal / feature / readiness rows | Core status |
| --- | ---: | --- | --- |
| 10:22:23 | 45 | 45 / 45 / 45 / 45 | CORE_PASS |
| 10:04:12 | 47 | 47 / 47 / 47 / 47 | CORE_PASS |
| 09:42:36 | 48 | 48 / 48 / 48 / 48 | CORE_PASS |
| 09:35:27 | 26 | 26 / 26 / 26 / 0 | CORE_FAIL |
| 09:22:31 | 47 | 47 / 47 / 47 / 47 | CORE_PASS |
| 09:04:19 | 46 | 0 / 0 / 0 / 0 | CORE_FAIL |
| 08:42:39 | 50 | 0 / 0 / 0 / 0 | CORE_FAIL |
| 08:33:50 | 30 | 30 / 30 / 30 / 0 | CORE_FAIL |
| 08:22:32 | 48 | 0 / 0 / 0 / 0 | CORE_FAIL |
| 08:04:47 | 49 | 0 / 0 / 0 / 0 | CORE_FAIL |
| 07:42:37 | 50 | 50 / 50 / 50 / 50 | CORE_PASS |
| 07:32:05 | 30 | 30 / 30 / 30 / 0 | CORE_FAIL |

**Aggregate:** 5 CORE_PASS, 7 CORE_FAIL. These 12 rows had `error_count=0`, including the incomplete scans, proving that parent error count alone does not establish successful persistence. Two recent core-pass scans are not evidence of repair or post-deployment monitoring.

**Scope:** These checks validate five core families (parent plus four child families) only. They do not certify all paper lifecycle, enrichment and auxiliary downstream side effects. Historical failures remain present and must not be rewritten.

## 2. Direct timeout evidence
Supabase unified log read-only window: 2026-11-07 07:30–10:25 UTC.

- PostgreSQL source: **16** log entries mentioning `statement timeout`.
- PostgREST source: **15** log entries mentioning `statement timeout`, error code **57014**.
- Counts are from two reporting streams and **must not be added** as independent failures.
- PostgreSQL records show an `alpha_hunter_symbol_snapshots` INSERT execution duration of **10,647.727 ms** at 10:22:36 UTC. This is one observed statement, **not** the scan p99.
- Timeouts visible around 08:05, 08:22, 08:42 and 09:04 UTC align with incomplete core scans. A log correlation is not proof that every missing record has the same independent cause.

## 3. Read-only deployment/trigger inventory
- Supabase Alpha Hunter project: PostgreSQL 17, active.
- **12** application triggers over **8** relevant public tables (per live catalog inspection).
- No `public.alpha_hunter_commit_core_scan_v01` function found in production catalog.
- Supabase development branches listed: none.
- GitHub PR #445 is a draft, unmerged candidate; independent review submissions: none in the inspected PR.
- Render production cron remained configured to run `hourly.py --once` on `main`. A 10:22 cron log recorded `trade_permission=false`; this is not an independent audit of all live-order controls.
- Candidate atomic RPC remains disabled by default in `alpha_hunter/storage.py`.

## 4. Stage-by-stage gate decision
| Stage | Gate result at this audit | Why |
| --- | --- | --- |
| 1 — Production protection & read-only core detection | **PASS (core detection only), continuous alerting NOT CERTIFIED** | Read-only checker reliably distinguishes latest known complete/incomplete core scans. Production was not modified. No proof of continuous monitor delivery. |
| 2 — Private production-faithful clone | **BLOCKED** | Existing schema-export helper requires privately supplied DB connection details; no authenticated private schema archive or faithfully restored nested trigger graph has been verified. |
| 3 — Full-graph performance | **NOT RUN** | Synthetic benchmark from PR does not substitute for actual trigger graph; production percentile hot path remains slow. |
| 4 — Atomic commit fault injection | **SYNTHETIC PASS ONLY** | PR isolated test evidence is not production-faithful DBA acceptance. |
| 5 — Independent DBA/security approvals | **FAIL / ABSENT** | No independent reviews on PR #445. |
| 6 — Controlled production recovery | **BLOCKED** | No production promotion or repaired canary authorised. |
| 7 — Post-recovery observation | **NOT STARTED** | 10 consecutive verified runs / 24-hour clock only begin after approved canary. |

## 5. Next required execution (single priority)
1. Prepare a **private**, read-only `pg_dump` or Supabase CLI schema export in the existing isolated Codespace; never commit secrets, function source, archives, or customer data to this repository. Follow `ops/local/export_private_pg_schema.sh` only after privately verifying connection, TLS, export compatibility and package scope.
2. Restore into offline PostgreSQL 17; inspect all dependent table/function/trigger/index/RLS/role objects; compare fingerprints using `ops/sql/readonly_core_scan_trigger_inventory_v01.sql`.
3. Populate **synthetic** production-shaped data, reproduce timeout and measure 30/50/61-symbol full-graph writes, including p95/p99, locks, WAL, I/O, rollback and side-effect identity.
4. Keep PR draft, atomic flag off, main unchanged and live orders disabled. Stop rather than changing production if cloning or signing requirements cannot be met.

**Final decision:** PRODUCTION REPAIR REQUIRED — NO-GO. No independent production certification asserted.
