# Alpha Hunter — Atomic Core Scan Write Release Gate (2026-11-07)

**STATE: BLOCKED — ISOLATED CANDIDATE ONLY, NO PRODUCTION CHANGE APPROVED**

This file is a review packet, **not** an implementation approval or a claim
that production now persists all evidence. Preserve the protected production
scanner, all live-trading prohibitions and the £0 spending limit.

## Confirmed incident

- Production Supabase contains an incomplete scan at 2026-11-07 08:04:47 UTC,
  whose parent declares 49 symbols and has 0 symbols, 0 signals, 0 features and
  0 readiness observations. Earlier 07:42 UTC scan has 50/50 in each family.
- PostgreSQL logs at approximately 08:05 UTC show timed-out inserts into
  `alpha_hunter_symbol_snapshots` with nested trigger activity.
- The observed trigger chain runs through strategy observations, decision
  quotes, execution freezes, and payoff-health percentile calculations.
- The 2026-11-07 live trigger inventory found 12 application triggers over
  eight relevant tables. The isolated test fixture implements a *synthetic
  subset*, not the actual full database functions or side-effect graph.

## New direct production baseline (read-only, 2026-11-07)

- `EXPLAIN (ANALYZE, BUFFERS)` on the 24-hour S3/LONG payoff-percentile
  SELECT (cutoff 2026-11-07 09:00 UTC) took **8018.312 ms** on the
  unmodified production database. This is one observed execution, not p95.
- The plan used `idx_ah_strategy_outcome_24h_time_episode_v02`,
  returned **160 rows** after filtering out **123,706 rows**, and
  reported 17,288 shared block reads. The full nested trigger can evaluate
  this query multiple times per scan, contributing to statement timeouts.
- The candidate partial index has NOT been installed or benchmarked on live
  data. Its 495k-row synthetic test is only directional evidence.
- PostgREST write receipts were corrected in
  `alpha_hunter/storage.py`: the atomic RPC now explicitly uses
  `Prefer: return=representation` instead of inherited `return=minimal`.
  The added regression test ensures a valid count receipt is mandatory.
- Isolated CI run 42360532943: 37 Python tests passed, PostgreSQL synthetic
  rollback/replay checks passed, percentile comparison passed.
- No further expensive live EXPLAIN should be performed without a scoped
  workload plan. No production DDL or scanner changes have occurred.

## Latest verified acceptance evidence (2026-11-07)

- A **read-only five-family acceptance query** now exists at
  `ops/sql/readonly_core_scan_persistence_gate_v01.sql`. It validates
  parent-declared symbol counts, all five core evidence families and two
  identity-lineage checks; it does **not** certify downstream paper lifecycle.
- Executing this query against production's 12 most recent inspected scans:
  **5 CORE_PASS / 7 CORE_FAIL**. Most recent checked 09:42 UTC is CORE_PASS
  (48/48 all five families); 09:35 UTC is CORE_FAIL (26/26 readiness 0/26).
  Old incomplete scans must remain immutable and visible.
- A 50-symbol isolated candidate test passed: all 50 rows in each child
  family, rollback of all five families on injected downstream error,
  replay with no repeated trigger side effects; malformed feature/readiness
  identity payloads are rejected before any writes.
- An additional synthetic `service_role` test passed with RLS enabled,
  and denies RPC EXECUTE to `anon` and `authenticated`.
- New isolated 50-query percentile hot-path benchmark (CI run
  `42362122063`, 495k synthetic outcomes) measured 1003.39 ms total
  baseline versus 511.39 ms with candidate index; candidate p95 query
  12.72 ms versus baseline 24.28 ms. Matched result counts identical.
  **This is not a production latency claim or full trigger benchmark.**
- CI at commit `7870086b131d56f048ad43ddf2affb84349ee4bf`
  succeeded: 37 Python tests, synthetic database integrity, RLS
  role simulation, and repeated 50-query latency test.
- Independent DBA/security review and faithful full-graph performance
  reproduction remain unsatisfied; production function and candidate
  index are still absent. No production write/deploy was performed.

## Engineering candidate

- `alpha_hunter/storage.py` includes an opt-in RPC client path.
  `atomic_core_scan_writes` is **false by default**.
- `ops/sql/atomic_core_scan_rpc_candidate_v01.sql` commits five core evidence
  families in one transaction, checks payload completeness, serializes
  same-run retries and uses anti-joins to avoid re-firing BEFORE INSERT triggers.
- The production feature enrichment trigger modifies `source_payload`; the
  candidate checks all non-enrichment fields and allows only documented
  geometry context keys to differ on replay.
- `ops/sql/strategy_payoff_percentile_hotpath_index_candidate_v01.sql` is an
  index *proposal*, never installed in production.

## Verified evidence

- Python regressions (36 tests) passed in Codespaces and the GitHub Action.
- PostgreSQL 17 isolated synthetic transaction tests pass:
  parent/child and downstream failures roll back; retry causes no repeated
  synthetic BEFORE/AFTER trigger side effects; immutable conflicts fail closed;
  caller permissions are restricted in the synthetic database.
- A prior test **failed** when a BEFORE INSERT trigger was added to the
  synthetic graph. The repair was revised to handle this; retain the failure
  and corrected run logs in the audit trail.
- Synthetic 495,000-row percentile query comparison: 26.25 ms baseline versus
  13.74 ms with candidate index in one isolated test; identical results.
  This does **not** prove production trigger throughput or p95 scanner latency.

## Mandatory independent DBA acceptance — NOT SIGNED

- [ ] Privately clone the production PostgreSQL schema, all transitive trigger
      dependencies, grants, indexes, function bodies, and representative
      sanitized data. Do not place private DDL, credential material, or customer
      records in this public repository or public CI logs.
- [ ] Verify each live trigger/function fingerprint and trigger ordering using
      `ops/sql/readonly_core_scan_trigger_inventory_v01.sql`.
- [ ] Compare candidate vs baseline on ≥30, ≥50 and max observed symbol scan
      sizes, including the *full actual nested trigger graph*.
- [ ] Measure wall-clock p50/p95/p99 and `EXPLAIN (ANALYZE, BUFFERS)` for
      the percentile hot path; compare response deadlines with the configured
      15-second HTTP timeout and allowed retry budget.
- [ ] Inject timeouts during symbols, feature enrichment, paper side effects,
      and final readiness writes; verify atomic rollback and zero orphan rows.
- [ ] Verify no duplicate strategies, shadow decisions, paper orders, ledger
      writes, or geometry-health records on post-commit retry.
- [ ] Verify successful replay, feature enrichment preserved, immutable
      source evidence, and all five required core record counts exactly match
      the scan.
- [ ] Provide independent DBA name, signed review, date, tested commit SHA,
      environment fingerprint, benchmark evidence, and explicit PASS/FAIL.

## Mandatory independent security acceptance — NOT SIGNED

- [ ] Review table grants, RLS, RPC EXECUTE privileges for service_role only,
      SECURITY INVOKER, search_path safety and definer-function side effects.
- [ ] Verify no `anon` or `authenticated` access to the new RPC; no secrets
      or sensitive DDL are disclosed in GitHub logs, commits or public endpoints.
- [ ] Verify the entire nested trigger graph cannot authorize live orders,
      transfer funds or weaken any trading/paper-only kill switches.
- [ ] Verify the function cannot be used for cross-run evidence mutation,
      spoofed trade permission or inappropriate idempotent identity reuse.
- [ ] Provide a separate qualified security-review signature bound to the
      **exact same release commit** as the DBA approval.

## Production release prerequisites — BLOCKED

- [ ] Both independent signatures received and checked against immutable commit.
- [ ] Production schema drift rechecked; query hot path benchmark accepted.
- [ ] Production index addition assessed for lock/CPU/disk impact, scheduled
      carefully; no unexpected spend (must remain £0).
- [ ] Rollback is rehearsed and approved; the scanner retains its original
      write path until explicit controlled promotion.
- [ ] Only after all checks: run **one authorised controlled production scan**
      through the repaired path (never a real trade), verify parent and every
      required child family for its unique new run_id, then inspect SQL logs.
- [ ] Roll back immediately on any mismatch, timeout or security deviation.
- [ ] Do not rewrite or delete the historical incomplete scans.
- [ ] No trading permission changes under any circumstance.

The user has **not** been asked to treat assistant/CI evidence as independent
human review. This document is not a release authorization.
