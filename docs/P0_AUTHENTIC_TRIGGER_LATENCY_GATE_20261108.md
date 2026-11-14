# Alpha Hunter P0 — Authentic trigger-graph SQL latency gate (8 November 2026)

**Status: BLOCKED — no authentic private restored PostgreSQL 17 clone verified, no authentic latency measurement obtained.**
**Branch:** `fix/supabase-write-timeout-qa`, draft PR #445. **Budget:** £0. **Release:** NO-GO. **Real trading:** disabled.

## What actually exists

- Read-only production catalog at **2026-11-08 17:22 UTC**: **131** enabled Alpha Hunter public application triggers, **110** private functions, **65** private SECURITY DEFINER functions; candidate core RPC and candidate payoff index both absent from live production.
- No Supabase development branches were present when checked.
- The public repository contains the isolated candidate RPC, synthetic-only PostgreSQL CI and read-only fingerprint inventory. This is **not** the private production source archive.
- GitHub connector cannot open the existing owner's private Codespace filesystem/session. A protected source archive, source-owner roles, dependency graph and authentic downstream test results remain unavailable for execution via this connection.

## Added concrete offline-only measurement runner

`ops/local/qa_authentic_pg17_rpc_latency_v01.py` is restricted to the **existing GitHub Codespace** and the **repair branch**. It refuses to run in GitHub Actions, against any nonmatching container or in the presence of a network interface.

Prerequisites enforced before an EXPLAIN ANALYZE measurement:

1. A preexisting **running** Docker container named `alpha-hunter-private-postgres17-qa` with **network mode none**; direct local Unix socket to database `alpha_hunter_private_qa`, PostgreSQL 17.
2. The production-inspected **110-function private custody digest**, including function bodies, ownership, ACL and runtime options, must match `8fae5afad12f3040d30d0416cbfd9be1` (this is a hash, not function SQL).
3. Exactly **131** enabled public Alpha Hunter triggers; candidate RPC with five JSONB arguments must exist in this **offline** clone only.
4. At least **500,000** rows of **synthetic** historical outcomes in the offline clone. This size check does **not** prove the data distribution matches production.
5. Three owner-only (`0600`) synthetic JSON fixtures in `$HOME/.alpha-hunter-private-dbqa/bench-fixtures/` named `30.json`, `50.json`, `61.json`, with directory mode `0700`. The base folder also must be `0700`. Each fixture contains `synthetic_only: true` plus the five core arrays `p_parent`, `p_children`, `p_signals`, `p_features`, `p_readiness`. Parent `run_id` must start with `QA_ISOLATED_`; no evidence may span run IDs or enable trade permission.

Each case uses two warmups and **20 independent rolled-back SQL trials** with `SET LOCAL ROLE service_role`, a **12-second statement timeout** and `EXPLAIN (ANALYZE, BUFFERS, WAL, FORMAT JSON)` on the real RPC. The SQL execution time excludes network/PostgREST. During **the same transaction**, the harness requires exact five-core-family row counts and positive coverage of all of these actual nested branches: observations, shadow quotes, freezes, payoff geometry, calibrated paper orders and 24-hour outcome queue. It then rolls the trial back.

If ANY required branch does not fire, if counts mismatch, if a real trigger times out, or if the identity/permissions/clone checks fail, the runner **blocks** instead of claiming a fast successful result. It prints only aggregate p50/p95/p99/max in milliseconds and safe pass/block classifications, never private SQL, payloads or credentials.

**Important:** This runner has been committed and unit-guarded, but **has NOT been run against an authentic restored clone**, nor are the required private fixtures known to exist. The 20-sample p99 is a small-sample descriptive estimate, not independently certified production tail behavior. A positive run is still insufficient for release because external gateway latency, actual source-custody contracts, background/extension effects, contention, distribution-matching and operational rollback require separate gates.

## Access and restoration boundary

Existing guarded private export: `ops/local/export_private_pg_schema.sh` (manual, hidden credential entry only inside authorized Codespace). Do **not** run it in CI or upload its archive or role inventory to GitHub/chat. GitHub tooling cannot obtain or manufacture private DB credentials. Production remains untouched.

Official Supabase self-hosted restoration documentation explains that **raw pg_dump includes Supabase internals** and can produce restore/permission incompatibilities, and that plain PostgreSQL may lack required Supabase extensions. Do not mistake a raw archive or an ordinary `postgres:17` instance for a fully equivalent restored Supabase instance. See https://supabase.com/docs/guides/self-hosting/restore-from-platform .

## Outstanding release gates

- Authorised operator securely obtains the private schema inside the existing Codespace, without public transfer.
- Restore the **real** nested trigger graph, matching roles/RLS, index definitions, extensions, function fingerprints and runtime settings in an isolated local PostgreSQL 17 instance. Record reviewed exceptions explicitly.
- Adapt synthetic fixtures to exercise the real branch conditions, verify downstream effects and percentile scientific equivalence, and measure realistic p50/p95/p99, locks, WAL, I/O, contention and concurrent publishers, both with baseline and candidate indexes.
- Independent DBA and security/custody reviewers sign exact release SHA; owner separately approves a rollback-ready canary before a controlled production change.
- Do not merge, modify the protected scanner, install production RPC/index, authorize real orders or spend.

**Decision: PRODUCTION NO-GO.**
