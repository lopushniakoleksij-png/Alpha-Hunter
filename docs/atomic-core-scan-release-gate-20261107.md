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
