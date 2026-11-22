# Alpha Hunter P0 — 22 Nov 2026 14:38 UTC: exact 14-Run Render-to-Supabase reconciliation

**SAFETY:** Read-only provider log searches and production `SELECT` only. No production changes, replays, backfills, reruns, credentials, access controls, deployment, trade-authority changes, or spend. The PR stays DRAFT/UNMERGED. **Release: NO-GO.**

## Grounded exact-source evidence

Queried the **original Render hourly cron service** `crn-d9nmbjbm8hqs73elu6hg` with bounded, non-overlapping one-hour windows on 22 November 2026 (10:00–14:38 UTC), with separate `Run ID:` and `Supabase:` application log filters. Aligned each log status with its exact timestamped run ID in the same service and then performed a read-only query against production Supabase for **those 14 exact IDs**, counting each of the four child families. These are *real publisher log IDs*, not payload-declared identity claims.

Column `counts` represents `declared symbol_count / symbol snapshot rows / signal rows / feature rows / readiness rows`. Rows below have parent `error_count=0`; all fourteen parents were present. The bounded searches returned no pagination for the sampled log lines.

| Render log UTC | Exact Run ID | Original Render application result | Production five-family counts |
|---|---|---|---|
| 10:06:07 | `a8671f9dcb668641d0d4685e5bde2164` | `SAVED` | 60/60/60/60/60 |
| 10:24:34 | `2f4a6e2873180a4b3397c00516aef00d` | `FAILED_HTTP_READ_15S` | 60/0/0/0/0 |
| 10:44:04 | `6873386ab523442e48be793726b4cd51` | `FAILED_HTTP_READ_15S` | 60/0/0/0/0 |
| 11:06:31 | `0906be2a4150e64fa502913e5db0680a` | `SAVED` | 60/60/60/60/60 |
| 11:24:22 | `12f37283d8f997d45e96de6345439bb8` | `SAVED` | 60/60/60/60/60 |
| 11:44:06 | `9b97f328355a5a2633a5b984f05fe538` | `FAILED_SQLSTATE_57014` | 60/0/0/0/0 |
| 12:06:19 | `d3f92af382b12646d5cce2b0002d4d23` | `FAILED_HTTP_READ_15S` | 60/0/0/0/0 |
| 12:24:20 | `6f54d99c83a0a6cdca09b90d04aa64cd` | `SAVED` | 60/60/60/60/60 |
| 12:43:58 | `aa3a2209d948d4b8d9c2fb11210e7c6f` | `SAVED` | 50/50/50/50/50 |
| 13:06:14 | `d98b5d6214b38f53811afcafa6d4afa1` | `SAVED` | 60/60/60/60/60 |
| 13:23:47 | `99beca2abaa4d51c058fe9efa941c942` | `SAVED` | 56/56/56/56/56 |
| 13:43:30 | `86c32506f7adab7a1a7495079fc15781` | `SAVED` | 52/52/52/52/52 |
| 14:05:49 | `a9f37cc14a9bd193d7b604588119d33c` | `SAVED` | 47/47/47/47/47 |
| 14:23:32 | `88d593ff281255611b2b26c5ad9d3822` | `SAVED` | 51/51/51/51/51 |

**Classification:** 10 `SAVED` application logs corresponded to ten runs with every one of five core-family counts equal to the declared symbol count. 4 `FAILED` logs corresponded to four **PARENT_ONLY** runs (parent declaring 60; all four child families 0): 3 HTTP read timeouts after bounded retries (15-second client timeout per attempt), and 1 HTTP 500 with PostgreSQL **SQLSTATE 57014** on upserting `alpha_hunter_symbol_snapshots` (statement cancellation). Exact source identity and count state are verified **at readback**, but cannot prove that every SQL attempt committed, when triggers fired, or what happens in paper/auxiliary ledgers.

The latest 50 mature scan parents as of ~14:38 UTC: **45 core-shape count matches, 5 parent-only**. Latest 12 mature scan parents: **10 count matches, 2 parent-only**. Parent timestamp of most recent incomplete scan **12:05:10.74689 UTC**, matched to log at 12:06:19 UTC for run `d3f92af382b12646d5cce2b0002d4d23`; latest sampled parent **14:22:47.586408 UTC**, matched to log at 14:23:32 UTC for run `88d593ff281255611b2b26c5ad9d3822`.

The provider cron execution events **07:00 through 13:00 UTC** all ended `status=successful`, including the hours with failed scan application logs. **Do not treat cron job success as persistence success:** the old deployed collector catches Supabase errors, prints `FAILED`, then returns zero, as established in `docs/P0_RENDER_FALSE_SUCCESS_EXIT_20261122.md`. The 14:00 provider run was still in progress at the event check.

## Technical and release implications

- Production failures are still **intermittent**, affecting both client read timeouts and PostgreSQL server-side 57014 cancellation. The 10 successful scan observations are consistent with recovery without a repair deployment; they do not prove a root-cause fix.
- The actual saved symbol population varied **47–60** in this cohort, rather than staying fixed at 60. Therefore keep 30/50/61 and concurrency/fault suites, and ensure authentic QA also exercises changing symbol universes and exact source-aware family counts.
- The proposed 5-family atomic function in draft PR #445 is **not deployed** to production; synthetic CI passing is insufficient for authentic production trigger/role/extension parity.
- Preserve failed historical run IDs without rewriting or backfilling them. Their absence of children is forensic evidence, not grounds for fabricating performance results.
- **Authentic release gate blocked** on original authorised private Codespace, protected PostgreSQL 17 schema archive, read-only exit-255 and backup checks, production-equivalent restored trigger/function/extension/RLS/role parity, genuine durable 30/50/61 concurrent throughput and 57014/read-timeout/lost-ACK/rollback full-downstream WAL/locks p95/p99, and two independent qualified DBA + security approvals. Only after these gates, seek separately authorised paper-only controlled rollout.
