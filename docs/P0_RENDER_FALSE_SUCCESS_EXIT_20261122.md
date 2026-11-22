# P0 — Confirmed false-success propagation in deployed Render cron (2026-11-22)

**Evidence timestamp:** approximately 06:48 UTC, 22 November 2026. **Scope:** read-only Render provider events/logs, Supabase SELECTs, and GitHub exact deployed source. Production release **NO-GO**.

## 1. Source-level defect identified in the EXACT deployed revision

Original Render cron service `crn-d9nmbjbm8hqs73elu6hg` latest live deployed commit is **`33e8820bc8e4e2958e2fc20c7fb80899c4e2e65e`** (October 6). Read that commit using GitHub `fetch_file(ref=<exact deployed sha>)`, not only current `main` or PR candidate.

At that exact revision, `alpha_hunter/collector.py`, `main()`, catches `SupabaseStorageError`, records `cloud_status = f"FAILED: {exc}"`, emits `Supabase: {cloud_status}`, and nevertheless ends with unconditional **`return 0`** (deployed file line 4226). Consequently `run.py`, `run()`, receives `main() == 0`, and `hourly.py` `run_once()` can see a successful scanner subprocess even if the Supabase persistence request has failed. In Render burst mode `run_render_cron_burst()` combines scanner process exit codes; the zero collector result masks the failed cloud write. This is a **confirmed code path for false-positive Render cron success**, not an inferred SQL root cause.

Draft repair PR #445 already changes `alpha_hunter/collector.py` to return `cloud_persistence_exit_code(enabled=...,status=cloud_status)` instead of unconditional zero. This returns **2** when configured persistence did not reach explicit `SAVED`. Existing offline regression `tests/test_p0_collector_cloud_persistence_exit_v01.py` asserts this fail-closed contract; `tests/test_p0_runner_cloud_persistence_exit_propagation_v01.py` verifies `run.py` stops before secondary writes when collector fails. **These candidate fixes have NOT been merged or deployed.**

## 2. Provider event + exact scan run-ID demonstration

Read-only Render logs on **2026-11-22 01:00–02:00 UTC** for original cron (independent `Run ID:` and `Supabase:` searches):

| UTC timestamp | Exact run ID printed by Render | Render persistence log |
|---|---|---|
| 01:06:18 | `37bfc566835a565c054ecaaef0f48a5a` | `Supabase: SAVED` |
| 01:24:44 | `a0ca34f62b80e9a5c4fe93415c74b0fa` | `Supabase: SAVED` |
| 01:44:15 | `198ad001379edf92b4fbf5d20f3baa6c` | `Supabase: FAILED` — HTTP read timed out after retries, client timeout 15 seconds |

Supabase exact run-ID SELECT for `198ad001379edf92b4fbf5d20f3baa6c` confirms parent at **01:43:17.34911 UTC**, `symbol_count=61`, `error_count=0`, **0 symbol, 0 signal, 0 feature, 0 readiness rows**. The discrepancy is not a declared publisher label; the run ID came directly from the original service log.

**Yet** Render authenticated provider events report the cron invocation starting **01:01:14 UTC** and ending **01:44:45.563798 UTC** with **`status=successful`**. This real 01:00 burst therefore shows that job-level success **does not certify even the final scan's core persistence**. The exact deployed `collector.py` unconditional-zero defect provides a code-level causal explanation for this false-success status. It does **not** prove the read timeout's PostgreSQL query/trigger cause or exclude other failure paths.

## 3. Live production integrity sample remains NOT certified

Direct Supabase SELECT-only latest **50 mature** parent runs (collected at least five minutes earlier): **41** core-shape count matches, **9** parent-only, no other child-count partials in this bounded sample. Latest **12**: **12/12** core-count matches, latest mature parent **06:43:15.994278 UTC**, but historic incomplete runs persist (last sampled parent-only **01:43:17 UTC**). Matching core counts do **not** validate all downstream lifecycle, payload content, side-effect cardinality or source custody.

Render provider reports all seven UTC hourly cron runs starting midnight through 06:01 ended `successful`; these job-level results must NOT override record-by-record verification. Production candidate `public.alpha_hunter_commit_core_scan_v01` and optional candidate index remain absent.

## 4. Release and independent-review controls

PR #445 at inspection: draft, unmerged, head `b3a0cb470a4a2c444cae39f13e1b7e0821604484`; **11/11** PR CI workflows concluded success; existing test suite validates the proposed exit-code fix only in offline/synthetic scope. Independent DBA and security reviews **0**, no named requested reviewers.

- **A1/B2/B3 still BLOCKED**: original owner's private Codespace terminal and protected PG17 schema archive inaccessible through connected GitHub tools; container exit-255 explanation and schema+function+trigger+RLS+grants+extension full parity unverified in restored `alpha_hunter_private_qa`.
- **Genuine 30/50/61 performance/atomicity still BLOCKED**: concurrent runs on authentic nested trigger graph, genuine statement/client timeouts, retry/lost ACK, rollback, all downstream effects, WAL, locks, p95/p99, signed independent DBA/security reviews.
- The confirmed deployed-code false-success defect is independent of the underlying persistence timeout defect. **Do not approve early deploy of either fix** without approved private QA, review and separately authorised paper-only rollout.
- No action in this investigation modified production, restarted the scanner, replaced a Codespace, installed RPC/index, merged code, enabled trading or incurred spending.

**Decision: P0 ACTIVE; PRODUCTION NO-GO.**
