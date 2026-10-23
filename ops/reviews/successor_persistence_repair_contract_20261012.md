# P0 persistence timeout root-cause gate and minimal successor-only repair specification
**12 October 2026 | Evidence-only | review required | DO NOT MERGE/DEPLOY DURING FROZEN R10**

## 1. Read-only causality check

Observed parent-only scan facts: seven parent snapshots in the rolling 24h had 0 persisted child symbols and 0 entry/exit attempts; the independently verified Render cron logs for those exact runs show six exhausted POST/read timeouts (15 seconds, three retries) and one direct `alpha_hunter_symbol_snapshots` upsert HTTP 500 / SQLSTATE 57014 PostgreSQL statement timeout. That is a **verified persistent-write failure mechanism**, not merely an omitted quote. The 8 October pilot's two parent-only runs also correspond to failed Supabase POST/read requests (see issues #339, #340).

Source `alpha_hunter/storage.py` `save_snapshot()` currently writes **parent first**, then children, then signals/features/readiness, then paper entries and finally position exit-monitoring. An exception after parent persistence can leave a valid-looking parent with no child or paper attempts. The upstream cause of load and exact trigger execution time is not yet isolated.

Exact SQL `successor_persistence_load_diagnostic_readonly_20261012.sql` executed from this draft (2026-10-12 11:06:52 UTC) returned:
- PostgREST `alpha_hunter_symbol_snapshots` insert/upsert statement: **1,014 executions since statistics reset**, weighted mean **3,841.6 ms**, observed maximum **11,847.6 ms**; **470,655** temp blocks written, ~**4.34 GB WAL**. This aggregate is historical/cumulative; not a 24-hour latency histogram or proof of individual trigger attribution.
- Service role `statement_timeout=12s`; Render client read timeout 15s. Never silently increase either as a fix.
- `alpha_hunter_symbol_snapshots` total **1,060,560,896 bytes** (of which **1,012,703,232 bytes** TOAST/other), `alpha_hunter_strategy_observations_v01` total **1,861,058,560 bytes**. This is real stored data, not cache or free-memory estimates.
- Verified AFTER INSERT/UPDATE trigger `trg_ah_capture_strategy_observations_v01` calls `private.alpha_hunter_capture_strategy_observations_v01()`, which loops strategy payloads and inserts immutable strategy observations and (where eligible) episodes.
- Rolling 24h `alpha_hunter_strategy_observations_v01`: **41,050** rows from **4,105** distinct symbol/run pairs on **69** runs, **exactly 10.00** strategy observation rows per symbol/run. Thus a ~60-symbol child upsert implies approximately 600 additional strategy observation inserts, before follow-on paper lifecycle stages; not evidence of 600 independent trade executions.
- Read-only inspection confirms the `(run_id,symbol)` unique key already exists, and no required index or trigger was added or dropped.

**Distinguish evidence from conjecture:** A high fanout and large row payload plausibly contribute to expensive symbol-snapshot upserts; exact proportion of latency attributable to strategy-trigger execution vs TOAST/WAL/I/O/contention remains UNMEASURED. No unreviewed trigger disablement, payload removal, index drop, search-path change or mutation is allowed.

## 2. Smallest future successor-only repair design, staged by risk

**A. Reliable completion evidence BEFORE optimising performance.**
- Create an isolated internal/least-privilege append-only `cycle-stage-receipt` contract, unique by canonical run + stage, with source commit/fingerprint, stage run/observed UTC, expected/observed child symbol identifiers, and captured `expected entry_order_id` set AS OF the run.
- Every verified stage emits `SUCCEEDED` with exact source IDs and committed rows; any observed partial stage emits `FAILED` with redacted SQLSTATE/HTTP class. A crashed worker with no terminal receipt is **MISSING/UNKNOWN** (not PASS).
- Final `COMPLETE` is permitted only after **persisted** parent and matching unique child rows; signals/features/readiness side-effect invariants as required by preregistered successor; entry-order reconciliation attempted/terminal state; **one verifiable exit-monitoring receipt per as-of-run filled paper position**; exact quote source/capture freshness, UTC time, valid bid/ask and side size. Zero positions requires an independently attested complete AS-OF snapshot.
- Preserve all original evidence rows. A new stage receipt is NOT a new R9/R10 scientific outcome, not an exit fill, stop hit, or backfill of missing 2026-10-08 / 2026-10-11/12 observations. The final receipt is append-only and cannot claim `COMPLETE` from the parent row alone.
- A receipt write itself may fail: independent read-only audit must treat no receipt as **FAIL/UNKNOWN**. Strict operational health must inspect stage proof, not scheduler status.

**B. Surgical write-path performance candidate, separately benchmarked.**
- Benchmark in a truly isolated database environment, using recorded **redacted/authorized representative payloads**, before and after, with existing strategy observation/episode content-preserving triggers: number of resulting rows and every deterministic ID must match for the same *fresh* run. Do not replay original production run IDs.
- First compare bounded child batch persistence vs direct bulk insert with current on-conflict upsert and trigger fanout; measure elapsed/lock and temp/WAL per transaction. Limit the scope to symbol-child persistence; do not change discovery strategy, cohort time, fees, thresholds, score, or number of generated observations as a 'performance win'.
- Candidate future-only implementation: a set-based strategy-observation writer or separate guaranteed/idempotent post-child stage with source-run durable receipt. This requires atomicity, no dropped per-symbol strategy evidence, no delayed scientific membership, no duplicate episodes and no double-hit on retry. **It is a candidate, not code merged or a production migration.**
- Preserve privilege boundary (security-invoker where appropriate, no exposed write APIs to anon/authenticated), reject arbitrary `run_id` replay, maintain deterministic conflict keys and checksum source identities.
- Do not merely shrink payloads: existing R9/R10 scientific geometry and historical valuation fields may depend on them. Preserve frozen commit/fingerprint and protected positions. A future successor needs an independent fingerprint and formal registration.

**C. Protection safety across incomplete cycles.**
- When a noncritical analytics persistence stage fails, do not report canonical `COMPLETE` and do not silently skip position monitoring. An independently reviewed future successor may isolate existing paper-position monitoring as a bounded, fresh-quote, independently persisted stage, but must preserve ordered transition semantics and no synthetic fills.
- A DB outage may prevent **all** writes, including a failure receipt. Fail closed, escalate missing verification; never report stop protection solely from two order records or a cron's successful exit code.
- Never breach the **35-minute maximum** between actual qualified position observations. Scanner heartbeat timestamps and a system-wide scan success are insufficient.

## 3. Falsifiable acceptance and rollback

For a **new** preregistered forward period, independent of R10, require: zero unexplained parent-without-child cycles, zero complete-cycle intervals >35min, full captured AS-OF position inventory and all per-position source-labelled attempts; no increased DB timeouts; no missing source field, stale capture, invalid top-book or duplicate run/position receipt; identical per-strategy row identity/content in control and successor for corresponding synthetic fixtures. On first failed stage or unknown coverage, block new successor admissions; protect existing positions. No threshold, order-authority, fee or profitability claim change.

Before any deployment, separately review DB load/trigger parity, security grants, migrations, temporary locks, DB resource cost, latency within bound, startup/rollback and the effect on the single running P0 and existing protections. **Rollback must not restart R10 or undo immutable data.** Current task only writes draft research and issues.

## 4. Gate status

- **Root-cause failure class: VERIFIED — database persist timeout; per-trigger contribution: NOT ISOLATED.**
- **Read-only pressure measurement: EXECUTED; original 12s statement limit retained.**
- **Successor-only protection/receipt contract: REVIEWABLE design; no production implementation.**
- **Production monitor completeness: FAILED; R10 admission halt / original 4 integrity failures unchanged.**
- **Deployment, cohort reset or live trade authority: NONE.**
