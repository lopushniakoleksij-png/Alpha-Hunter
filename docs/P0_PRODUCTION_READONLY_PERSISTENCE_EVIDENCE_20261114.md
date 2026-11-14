# Alpha Hunter P0 — 14 Nov 2026 production read-only persistence investigation

**Status: ACTIVE P0 — PRODUCTION NO-GO.** This is a sanitized engineering-evidence summary, **not** an independent release certificate.

## Evidence and provenance

- Source: connected Alpha Hunter production Supabase project, **SELECT-only** queries against the latest 50 parent scans and their child counts, executed 2026-11-14 around 12:06 UTC. Neither SQL nor connector calls modified production.
- Source: Render **read-only** cron service metadata, events and log filters from 2026-11-13 20:30 to 2026-11-14 12:10 UTC.
- Source: GitHub `main` collector and scan launcher, plus repair candidate on draft PR #445.
- Do **not** publish credentials, parent payloads, database DDL/function bodies, run IDs, tenant details, raw logs, or private backups. Source labels in parent JSON are **self-claims, not independently authenticated publisher identities**.

## Production scan persistence

| Scope (collected_at_utc) | Evidence |
| --- | --- |
| Latest 12 parent scans through 2026-11-14 12:05:04 UTC | **12/12** meet exact five-family row counts (parent-declared symbols, symbols, signals, features, readiness), no feature/readiness orphans, zero scan errors |
| Latest 50 parent scans, 2026-11-13 20:43 through 2026-11-14 12:05 UTC | **38/50 complete; 12/50 incomplete** |
| Incomplete subset | All **12** had zero symbol, signal, feature and readiness child rows despite nonzero parent symbol_count |
| Latest incomplete parent | 2026-11-14 07:23:08 UTC |
| Product/version | All 50: `usdt-futures` / `0.7.1` and contract `snapshot-parent-v0.2` |
| Parent-reported writer `RENDER_CRON` at commit prefix `33e8820bc8e4` | 47 samples: 35 complete, **12 parent-only** |
| Parent-reported writer `GITHUB_REALTIME_HOURLY` / `GITHUB_ACTIONS` at prefix `b71c87d0b596` | Three samples, all complete |

These last source labels are untrusted parent metadata until corroborated with Render/GitHub event custody. The aggregate shows recent *intermittent* parent-only publication; the last 12 successes do **not** close P0.

## Direct Render failure evidence

Read-only Render cron logs contained **12** `Supabase: FAILED` messages in the selected time range:

- **8** HTTP 500 PostgreSQL SQLSTATE **57014** errors: `canceling statement due to statement timeout` while upserting `alpha_hunter_symbol_snapshots`. Example at **2026-11-14 07:24:09 UTC**, close to the latest incomplete parent at 07:23:08 UTC.
- **4** exhausted HTTP request retries (`Read timed out`, configured **15 s** client read timeout, **3 attempts**).
- Render cron run history includes a `successful` service-level run end at **2026-11-14 07:44 UTC**. Service-level success does **not** prove all parent and child writes persisted.
- This is strong evidence for the recurring symptom, but raw request/run-id correspondence, lock/WAL pressure, transitive nested triggers, and exact timeout-causality still require protected investigation.

## Concrete source defect and candidate correction

The deployed `alpha_hunter/collector.py` catches `SupabaseStorageError`, prints `Supabase: FAILED`, but then **always returns 0**. The caller `run.py` therefore receives a successful collector exit even when cloud persistence fails; the Render burst's final status can be successful.

On the existing **unmerged draft repair branch only**, added `cloud_persistence_exit_code` and return propagation:

- Configured Supabase persistence `SAVED` => return 0.
- Configured Supabase `FAILED`, `NOT_CONFIGURED` or any non-`SAVED` => return 2.
- Supabase explicitly disabled => preserve offline local-scan success.
- No order execution, trading switch, production scanner configuration, deployment, database DDL or production data was changed.

Commits: implementation `082f0299de8b91b3f38d9ddbfb0cfb689a0082ae`; focused tests `68b5a5fec53e251a970d8a671b6f75bc86322caf`.

Exact test commit completed **GitHub Full Production Test Suite: 1460 passed + 101 subtests**; PostgreSQL contract and scientific fingerprint workflows SUCCESS. This verifies *mocked fail-closed exit status and static wiring*, not live Render behaviour.

A read-only production catalog check found `public.alpha_hunter_commit_core_scan_v01(jsonb,jsonb,jsonb,jsonb,jsonb)` **not installed**. The candidate atomic parent/child RPC remains disabled/unreleased.

## Mandatory gates before production repair approval

1. Recover and inspect private Codespaces QA container safely after its previously observed exit **255**. Do not restart blindly, delete the container, export private SQL into public GitHub or change permissions to bypass guards.
2. Authenticate private production-schema/fingerprint equivalence and run controlled **same-run and different-run concurrent** full-graph tests; measure p50/p95/p99 durable commit + WAL/lock/statement/HTTP timeouts against realistic workloads.
3. Inject timeout/lost-ack/failure at every core and nested downstream family; verify zero orphan writes, identical idempotent retry receipts, no duplicate paper-side effects and strict release-candidate controls.
4. Independently verify which producer emitted each incomplete parent; maintain source-custody watch and protect the legacy-writer retirement gate.
5. Obtain separate qualified DBA and security reviews/signatures tied to an immutable exact commit; approve £0 rollout/rollback and paper-only controlled trial.
6. **Only after approvals** explicitly authorize release of atomic RPC/index/collector logic, then verify a freshly generated production scan end-to-end. Do not rewrite historical incomplete scans or allow real orders.

**No merge, migration, deployment, cost, production scanner change or real-money trading authorisation.**
