# Alpha Hunter — P0 live production integrity checkpoint (17 November 2026)

**Decision: ACTIVE PRODUCTION NO-GO.** Read-only investigation only; no production changes, migration, live order authority or new scanner.

## Scope and provenance

- Queried the connected Alpha Hunter Supabase production project around **2026-11-17 22:15 UTC** via **SELECT-only** recent parent/child aggregate queries. No run IDs, secrets, SQL source bodies or raw records are published here.
- Read-only Render cron logs for the **2026-11-17 17:00–22:15 UTC** window, service ID held in connected Render workspace. Results below count log messages in this window, not unique root-cause incidents.
- Examined draft PR #445 (branch `fix/supabase-write-timeout-qa`, HEAD `8507691de3606683e361390fe524bd80486c8e20`) and its exact-SHA checks. PR remains unmerged.
- `validation_identity.run_source` and commit fields are **self-reported metadata**, not authenticated proof of publisher identity.

## Production: recent scan-persistence regression

| Read-only sample | Core-shape complete | Parent-only (zero child rows) |
|---|---:|---:|
| Latest 50 parent scans | **22 / 50 (44%)** | **28 / 50 (56%)** |
| Latest 12 parent scans | **4 / 12 (33.3%)** | **8 / 12 (66.7%)** |
| Earlier 38 of same 50 | 18 / 38 | 20 / 38 |

Core-shape complete requires `error_count=0`, symbol child count equals parent-declared `symbol_count`, signal count equals feature count and readiness count equals declared symbol count. **Core-shape match does not certify all downstream strategy/paper-science evidence**. Parent-only requires nonzero parent symbol count and zero rows in symbol, signal, feature and readiness tables.

Latest observed parent at **2026-11-17 22:05:01 UTC** is **parent-only**. The sample is rolling, not a random population or a long-term failure probability. By comparison, 14-Nov audit reported 38/50 complete; the 17-Nov deterioration applies to a **different rolling window**.

**Source-metadata stratification (latest 50):**
- `RENDER_CRON`, runtime `RENDER_CRON`, claimed writer commit prefix `33e8820bc8e4`, storage contract `snapshot-parent-v0.2`: **48 scans / 20 complete / 28 parent-only**.
- `GITHUB_REALTIME_HOURLY`, runtime `GITHUB_ACTIONS`, claimed prefix `b71c87d0b596`: **2 scans / 2 complete**.
- These are reported source labels only; independently tie each run to genuine Render/GitHub execution IDs before a publisher attribution is certified.

## Corroborating Render failures

Read-only Render log filter `Supabase: FAILED` for **17:00–22:15 UTC** returned **nine messages**:
- **5** PostgreSQL HTTP-500 / SQLSTATE `57014` statement timeouts, all visibly referencing upserts to `alpha_hunter_symbol_snapshots`.
- **4** HTTP client read timeout messages.
- Latest message: **22:05:59 UTC**, close to latest parent-only scan at 22:05:01. Temporal association is not exact request-to-run ID proof.

## PostgreSQL observations — read-only only

- Candidate atomic RPC **absent from live production**, so the existing non-atomic writer remains in service.
- Installed `pg_stat_statements` v1.11 and `pg_cron` v1.6.4. Current sampled `pg_stat_activity` client sessions mostly waited on client input; this snapshot does not prove lock wait absence during failures.
- `pg_stat_statements` was last reset on **2026-09-30 22:01:58 UTC**, so these cumulative figures are **NOT time-bounded to 17 November**:
  - Queries containing `alpha_hunter_symbol_snapshots`: **10,985 calls** across 1,052 normalized query entries, cumulative execution time **32,141,092.9 ms**, maximum observed single execution **110,176.1 ms**, 26,036,047 shared block reads.
  - Queries containing `alpha_hunter_readiness_observations_v01`: **3,071 calls**, cumulative **118,844.8 ms**, maximum **8,346.1 ms**.
  - Queries containing `alpha_hunter_strategy_forward_outcomes_v01`: **14 calls**, cumulative **22,799.8 ms**, maximum **8,076.5 ms**.
- These normalized-query groups use a text match and can overlap nested trigger work. They neither locate one definitive root function nor establish current p95/p99, locks or throughput. **Do not reset statistics or run expensive EXPLAIN in production without an approved workload plan.**

## Repair status and required engineering decisions

- Draft branch repairs already contain an opt-in five-family atomic RPC and fail-closed configured Supabase error exit; the production scanner still uses the older writer.
- Latest exact-head GitHub CI at `8507691de3606683e361390fe524bd80486c8e20`: 11/11 workflows SUCCESS (full suite **1,481 passing tests + 101 subtests**). These do **not** certify production transaction behaviour, authentic trigger/role equivalence, private QA concurrency or a 12-second RPC HTTP deadline.
- Private Codespaces QA container last observed exited with code **255**; no verified current Docker state, archive custody, private schema restore or DBA-authorised recovery was accessible through connected tools.
- The next **critical path** is A1/B2/B3 in `docs/P0_REPAIR_COMPLETION_EXECUTION_BOARD_20261114.md`: recover the same isolated private QA reference after diagnosis; verify authorised private schema and role/trigger/index fingerprints; then run genuine same-/different-run concurrent writes, fault injection, full downstream ledger and HTTP latency tests before qualified DBA and security review.
- No merge/deploy, production DDL, scanner restart, new spend or real-money trading is authorised; do not treat a successful Render scheduled job as proof of child persistence.

**Custody boundary:** publish sanitized aggregates only. Archive, credentials, raw DB functions, SQL bodies, detailed logs and sensitive source manifests remain private.
