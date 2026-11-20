# ALPHA HUNTER — P0 read-only persistence and Render correlation — 2026-11-20

**Snapshot time:** approximately 20:24 UTC, 20 November 2026. **Status: PRODUCTION NO-GO.** No scanner restart, production SQL mutation, deploy/merge, trading-authority change, private restore or spending. All results are only as of this checkpoint.

## 1. Actual production Supabase recent scan readback

Read-only SQL over the latest 50 parent runs **older than a 5-minute in-flight grace period**, ordered by `collected_at_utc DESC`. For core-shape complete require `error_count=0`, symbol rows = declared parent symbol count, signal rows = feature rows, readiness rows = declared parent symbol count. This is not full downstream/paper evidence certification.

| Sample | Core-shape complete | Parent-only (zero symbol, signal, feature, readiness children) | Other partial children |
|---|---:|---:|---:|
| Latest 50 | **45/50** | **5/50** | **0** |
| Latest 12 | **8/12** | **4/12** | **0** |
| Earlier 38 in same rolling sample | **37/38** | **1/38** | **0** |

Latest observed mature parent: **2026-11-20 20:05:49 UTC**, declaring 60 symbols with 60 symbol and 60 readiness rows. Latest identified parent-only: **17:44:05 UTC** (60 declared symbols, zero children). All eight runs after 17:44:05 in the latest-12 display have matching symbol and readiness counts, as well as core family-count agreement in the aggregate query. These are **observations**, not evidence of permanent repair; the 17:44 parent remains incomplete.

Self-reported source labels in parent JSON, **not authenticated identities**:
- `RENDER_CRON`: **47 runs / 42 core-shape complete / 5 parent-only**.
- `GITHUB_REALTIME_HOURLY`: **3 runs / 3 core-shape complete**.
Source claims must be bound to provider run IDs/logs before definitive attribution.

## 2. Render cron independent log evidence

Queried connected original Render `Alpha-Hunter` cron resource for **2026-11-20 13:00–20:24 UTC**, filter `Supabase: FAILED` and limit 100. Returned **15 matching log messages**, `hasMore=false`. All **15** returned messages were classified as **HTTP read timeouts**; do not interpret as the complete set of all error types on the service. First at **13:08:10 UTC** and last at **17:46:22 UTC**, close in time to the 17:44 incomplete parent. Temporal correlation supports the legacy writer investigation but does **not** prove individual request→run causality.

Direct Render service config: branch `main`, command `python3 hourly.py --once`, cron `0 * * * *`. Latest **live deployed commit** is still **`33e8820bc8e4e2958e2fc20c7fb80899c4e2e65e`** (2026-10-06), **not** PR #445. No restart/deploy attempted.

## 3. Current repair candidate and production status

Connected production Supabase catalog confirmed `public.alpha_hunter_commit_core_scan_v01` candidate atomic RPC **not installed**; proposed candidate payoff index **not installed**. Do not treat healthy post-17:44 writes as a release of the repair.

GitHub PR #445 head at this checkpoint: `dc066e84ffc89c79993322815b218d9ed932c534`, **OPEN, DRAFT, UNMERGED**, **zero submitted reviews**. All **11/11 exact-commit GitHub CI workflows SUCCESS**. Full-suite log `https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/44784463072`: **1,611 passing Python tests plus 101 subtests**. This validates isolated code/test contract only, NOT production atomicity or authentic private PostgreSQL performance.

## 4. Remaining irreducible release dependencies

- **A1**: obtain owner-authorised access to original private Codespace, inventory old PG17 container exit 255, preserve volumes/backup and private archive custody before any restart.
- **B2/B3**: restore approved schema-only archive and no-password roles to the **existing network-none private QA environment**, verify the exact full production-equivalent fingerprint set, extension schema/version, function ACL/owner and nested trigger DAG, distinguishing Stage 7 reference `ah_authentic_schema_20261110` from full-parity target `alpha_hunter_private_qa`.
- **C/D**: genuine 30/50/61 and peak symbol durable concurrent transactions and service-role HTTP p50/p95/p99, SQL 57014/read timeouts, lost ACK, retry, rollback, downstream identity/duplicate/orphan verification and WAL/locks/IO. Prior synthetic CI and isolated Stage 7/8 evidence do **not** discharge this.
- **F**: independent named qualified DBA and security reviewers must each examine immutable evidence and provide explicit signed decisions; owner then separately approves controlled paper-only release and rollback. **Reviewers not yet requested; none approved**.

**Do not use historical repair QA tests as evidence that production is fixed; preserve single canonical scanner, paper-only status, no new paid environment and real orders disabled.**
