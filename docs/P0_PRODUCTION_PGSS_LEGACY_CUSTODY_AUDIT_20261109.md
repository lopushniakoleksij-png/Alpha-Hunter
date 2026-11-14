# ALPHA HUNTER — P0 PRIVATE-CLONE RELEASE BLOCKER AND LIVE SQL PRESSURE (9 Nov 2026)

**Scope:** forensic read-only production metadata and log aggregates; £0; paper-only; protected scanner unchanged. **Release decision: PRODUCTION NO-GO.**

## 1. Authentic clone and nested-trigger benchmark

**NOT RESTORED. NOT MEASURED.** The connected Supabase project has **zero development branches**. GitHub can edit the public repair branch but cannot directly read the owner's existing Codespace private filesystem or obtain an authorized schema archive. Available file search located an incident-analysis note, **not** the private schema archive. Do not copy private function source, production credentials, real records, IP addresses or JWT fragments into this public repository.

Production catalogs were previously verified: 131 enabled public application triggers, 110 private functions, including 65 private SECURITY DEFINER functions. Fingerprints and role/extension fidelity remain mandatory to approve a private clone. The existing offline-only QA runner is `ops/local/qa_authentic_pg17_rpc_latency_v01.py`. It has not been executed against an authentic clone, therefore **p95/p99 authentic trigger-chain numbers do not exist**.

## 2. New real production SQL timing evidence

Read-only `extensions.pg_stat_statements` audit on **9 Nov 2026 at approximately 00:49 UTC**:
- Statistics cumulative since **2026-09-30 22:01:58 UTC**, not a current-run time window.
- `pg_stat_statements.track=top` and `track_functions=none`: **no nested trigger-function latency breakdown** is captured.
- Dominant statement family references `alpha_hunter_symbol_snapshots`, contains `INSERT` and `ON CONFLICT`, statement fingerprint **153440d36d3f**:
  - **2,991 calls**
  - **4,824.38 ms mean**, **11,881.16 ms maximum**
  - **14,429,709.33 ms accumulated execution time**
  - **12,600,566,363 write-ahead-log bytes** since stats reset.
- A prominent feature-statement family (fingerprint `e3f5f356119c`) records **3,800 calls**, **630.04 ms mean**, **5,865.23 ms max**, **2,744,772,409 WAL bytes**.
- These are top-level statement statistics, not direct measurements of specific trigger functions or individual failed 57014 calls. The query classification is by referenced tables and SQL shape, **not proof that all time belongs exclusively to one table**.
- A reproducible **read-only, redacted profiler query** is committed at `ops/sql/readonly_pg_stat_core_upsert_pressure_v01.sql` and was successfully executed against live Supabase. It returns only numeric statistics and opaque 12-character SQL fingerprints, never query bodies.

### Interpretation

Top-level symbol UPSERT and WAL pressure are now **measured**, strengthening the known trigger fan-out/write-amplification hypothesis. The candidate atomic function avoids redundant UPDATE-trigger replay on idempotent retries, but the first-write authentic graph, side effects, permissions and concurrency still require the private clone. **Do not infer the fix works in production from these statistics.**

## 3. Obsolete publisher request custody

Read-only **Supabase edge logs** grouped by network organization, Python client, method and request path, within the last 24-hour window:

- Obsolete full-parent writer: **5** observed parent POSTs, legacy client `python-requests/2.32.5`, service-role JWT metadata, external non-Render/non-GitHub network organization; correlated with the old Python storage implementation that persisted full nested `intelligence` and did not write readiness.
- Its last observed **any-category** API request in that cohort was **2026-11-08 17:27:27 UTC**. **No subsequent requests in the inspected log window**; this does not prove shutdown or removal.
- Current Render and GitHub scanners use `python-requests/2.34.2` in the observed cohort, from their expected network classes.
- The old publisher and GitHub-hosted requests share a logged **JWT signature prefix** (comparison performed inside ClickHouse; **no signature bytes exported**). This is evidence of a **possibly shared service_role credential** rather than proof of identity. Blind JWT/key rotation could disable the protected GitHub hourly scanner.
- The exact obsolete process, machine, credential custody and scheduling authority have **NOT** been established. Network-provider metadata is not device identification.

### Safe retirement boundary

**No retirement performed.** Do not revoke a possibly shared service-role JWT, alter RLS, delete evidence, disable the protected scheduler or block network/provider ranges. A controlled retirement requires locating the obsolete process in an authorized inventory, disabling only that process, verifying protected Render/GitHub continuity, separating credential custody, then rotating an isolated legacy credential if and only if the legitimate writers remain functional. This still requires operator access/approval; the linked GitHub and Supabase read-only tools cannot manipulate an unseen local desktop or Codespace process.

## 4. Next verifiable gates

1. **Private, authorized schema archive into existing Codespace** (owner-only path; no public upload) or an approved cost-free, isolated private equivalent.
2. **Exact clone comparison**: 131 triggers, complete nested functions and role/ACL/RLS/index/extension fingerprints, no unreviewed differences.
3. **Authentic trials**: 30/50/61 synthetic symbols through the restored authentic functions; verify both all five core families and all required downstream branches, true rollback, realistic concurrency, WAL, locks, p50/p95/p99 and p99 uncertainty.
4. **Publisher custody**: identify exact obsolete process; confirm it is stopped, using independent request/log evidence without compromising current scanner.
5. Independent DBA/security sign-off at exact commit; explicit owner authority for a canary release and rollback; no real-order capability.

**Main protected, PR #445 stays draft and unmerged; no production schema changes, execution-authority changes or spending.**
