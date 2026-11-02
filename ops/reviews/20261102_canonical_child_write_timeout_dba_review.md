# Alpha Hunter P0 — 2 November 2026 canonical child-write timeout

**Status: ISOLATED REVIEW ONLY. NO PRODUCTION DATABASE CHANGE, NO MERGE OR DEPLOY.**

## Directly verified read-only production evidence
- At 08:23:20 UTC, RENDER_CRON snapshot parent 305fa28308441abd5fb74bf2886eac69 expected 61 symbol children, stored 0.
- At 08:05:45 UTC, previous parent 714535034e77f6e9ea38bbb7d4f7c0ff stored 61/61.
- At 08:28:31 and 08:29:57 UTC, Render web logs show RuntimeError: Incomplete compact canonical snapshot child evidence. The fail-closed guard is correct.
- At 08:24:20 UTC, scanner logs show HTTP 500 and SQLSTATE 57014 for alpha_hunter_symbol_snapshots upsert. Supabase PostgreSQL logs at 08:23:51 and 08:24:06 UTC corroborate the failing upsert.
- PostgreSQL error context traces child upsert -> capture_strategy_observations_v01 -> shadow decision quote capture -> execution decision auto-freeze -> capture_payoff_geometry_health_v01. The last trigger function runs repeated percentile_cont calculations on strategy_forward_outcomes_v01.
- The current index idx_ah_strategy_forward_outcome_strategy_v01 covers strategy_id, horizon_hours and evaluated_at_utc, but the baseline EXPLAIN still post-filters direction, entry trigger status, quality, ordering ambiguity and percentile non-null status.
- Read-only query returned 113,138 horizon=24 outcomes; just 1,127 satisfied the combined quality filter.
- Separately, an internal MONEY_SCORECARD pg_cron query timed out at 08:31 UTC. This suggests possible wider resource pressure; an exclusive root-cause attribution or a proven permanent fix is NOT claimed.
- Supabase project reported ACTIVE_HEALTHY. Direct SQL read-only queries succeeded.

## Candidate
See 20261102_payoff_health_index_CANDIDATE_NOT_FOR_PRODUCTION.sql in the same folder. It proposes a narrow partial covering index for the percentile query, to avoid reading irrelevant outcomes during nested trigger invocation.

This index adds database space and write overhead. It may not fix all timing issues. It has not been created in production or performance-tested in an isolated database. PR #371 and PR #372 independently propose write batching and fail-closed parent publication; this candidate is complementary and must not weaken those protections.

## Mandatory independent gates before any change
1. Benchmark the exact SQL and nested trigger chain with realistic data on isolated PostgreSQL 16 and PostgreSQL 17. Baseline p50/p95/p99 latency, EXPLAIN ANALYZE BUFFERS, DB load and space.
2. Create this candidate index only in isolated databases; prove output-value equivalence, plan improvement and end-to-end 61-symbol batch durability under both ordinary and concurrent load, including retries and timeout errors.
3. Test rollback in isolation using: DROP INDEX CONCURRENTLY IF EXISTS public.idx_ah_payoff_health_24h_strategy_dir_eval_v01; . This statement must not be wrapped inside a transaction.
4. Confirm safe PostgREST 500/ambiguous-write handling, parent-child completeness and independent position protection; no incomplete parent may become verified.
5. Obtain independent DBA/security and production release approval. Keep the P0 Render scanner, sealed 30-day experiment, R10 admission halt, positions, and frozen 35-minute monitoring limit unchanged. Main commits auto-deploy the production cron, so DO NOT MERGE automatically.
6. On an approved successor release only, recheck canonical child records, protection evidence and both /api/latest and / UI. Never display a stale scan as current data.

**Decision: CANDIDATE PREPARED / PERFORMANCE UNVERIFIED / PRODUCTION NO-GO.**
