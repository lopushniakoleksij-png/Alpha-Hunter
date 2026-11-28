# ALPHA HUNTER — Production Scan Persistence Incident
## Evidence-backed technical audit and controlled recovery plan — 2026-11-07

**Incident:** P0 data-integrity failure (not proof of scanner outage).
**Production project:** Supabase PostgreSQL 17.6, EU West 1.
**Scope:** Only Alpha Hunter Supabase persistence and its synchronous database trigger graph; protect main, active scanner, paper positions, market-data custody, real-order kill switch and £0 spending rule.
**Audit basis:** Direct read-only production SQL and logs, existing repair branch code, pull request and successful isolated GitHub Actions runs. No production mutation, migration, trading order, credential rotation or deployment was performed in this audit.

### Executive decision
**Production release = NO-GO.** Existing live code can publish a parent scan record while zero or only some required child evidence persists. The candidate repair is promising and has passed *synthetic* tests, but no independent DBA/security signatures or representative full-trigger replica exist. Do not merge, enable the feature flag, create production indexes, install the RPC or claim repair until the release checklist below passes.

## A. Quantified live impact

Read-only query on latest **50** parent scans, from 2026-11-06 20:23:04 UTC through 2026-11-07 10:04:12 UTC:

| Measurement | Directly observed |
|---|---:|
| Complete five-family core scans | 37 of 50 (74%) |
| Incomplete core scans | 13 of 50 (26%) |
| Parent present but all symbol children absent | 7 scans |
| Symbol, signal and feature present but readiness absent | 6 scans |
| Missing symbol-child rows vs parent declarations | 343 |
| Missing readiness rows vs non-error expected counts | 513 |
| Largest parent-declared symbol count in cohort | 61 |

All 13 incomplete samples had parent \`error_count=0\`; parent-level success/error metadata alone therefore fails to detect persistence errors. Examples:
- **09:04 UTC:** 46 declared symbols, 0 symbol/signal/feature/readiness rows.
- **09:35 UTC:** 26/26 symbols/signals/features, but 0/26 readiness rows.
- **09:42 UTC:** 48/48 for all four child families — an intermittent pass, NOT proof of repair.

The five-family read-only gate is in \`ops/sql/readonly_core_scan_persistence_gate_v01.sql\`. Current gate covers core evidence and orphan feature/readiness lineage; paper lifecycle and more remote downstream side effects must be evaluated separately. Historical incomplete runs are immutable evidence; do not delete, relabel or fabricate them.

## B. Confirmed SQL/log findings and probable root causes

1. **Non-atomic client writes (confirmed):** \`alpha_hunter/storage.py\` currently defaults \`atomic_core_scan_writes=False\`. Its legacy \`save_snapshot\` path issues separate REST upserts, in order: parent, symbol children, signals, signal features, readiness. If any later request times out or fails, earlier transactions may already be committed. This directly accounts for the observed zero-child and missing-readiness classes.
2. **Expensive nested synchronous trigger path (confirmed structurally, strongly supported as timeout driver):** symbol-snapshot INSERT/UPDATE of payload activates strategy observations; those can activate shadow decision quotes, then execution freezes, then payoff geometry health, plus paper-order/ledger side effects. The payoff trigger performs four \`percentile_cont\` calculations in *one SQL aggregate* over \`alpha_hunter_strategy_forward_outcomes_v01\`, filtered by strategy, direction, 24-hour horizon, quality, trigger status, and evaluation cutoff.
3. **Actual latency evidence (direct):** one prior read-only \`EXPLAIN (ANALYZE, BUFFERS)\` of that representative payoff SELECT took **8018.312 ms**. PostgreSQL scanned 123,866 candidate rows (123,706 discarded, 160 matched), 17,288 shared block reads, via \`idx_ah_strategy_outcome_24h_time_episode_v02\`. This is one cold-ish sample, not p95 and not a measurement of the full trigger workload. Do not repeat expensive production EXPLAIN casually.
4. **Real PostgreSQL timeouts (confirmed):** \`postgres_logs\` show \`canceling statement due to statement timeout\` at 08:05, 08:22–08:23, 08:42–08:43, 09:04–09:05 and 09:43 UTC on 2026-11-07. They temporally support the incident; do not claim each log is individually linked to a specific scan without request/transaction correlation.
5. **Database size (direct):** the strategy forward-outcomes relation was estimated at **477,060 rows** and **233 MB including indexes** at audit time. Existing indexes are not optimized specifically for the compound percentile predicate. Production did not have the candidate partial covering index installed.
6. **Timeout configuration nuance:** the isolated SQL-editor session showed \`statement_timeout=2min\`; this is NOT proof of the active REST session's timeout. The Python storage client configuration defaults to a **15-second HTTP timeout**, two retries and 1-second starting backoff; independently verify effective deployed scanner configuration, PostgREST and role-specific statement timeouts.
7. **Trigger inventory and security:** 12 app triggers across eight relevant tables (10 distinct functions) were fingerprinted read-only. Several downstream functions (including paper-order generators and geometry enrichment) are \`SECURITY DEFINER\`; their grants, predicates, side effects, trigger ordering and production hashes must be reproduced in private QA. Wider production schema has 144 user triggers. Do not disable or rewrite triggers on production without a reviewed replacement.

**Root-cause confidence:**
- HIGH: partial persistence is caused by multiple independently committed API requests.
- HIGH: an expensive payoff-percentile query is executed as part of the synchronous symbol-write trigger graph and can materially contribute to timeouts.
- NOT YET PROVEN: exact latency contribution and failure frequency of every nested production trigger; relative effects of CPU, I/O, locks, statement deadlines and concurrent activity; security and full lifecycle completeness under the atomic candidate.

## C. What is repaired in the isolated branch

Draft PR [#445](https://github.com/lopushniakoleksij-png/Alpha-Hunter/pull/445), branch \`fix/supabase-write-timeout-qa\`, **unmerged**:

- \`ops/sql/atomic_core_scan_rpc_candidate_v01.sql\`: one SECURITY INVOKER PostgreSQL RPC transaction for parent, symbols, signals, features and readiness; per-run advisory lock; replay anti-joins to avoid duplicate trigger effects; persisted content and signal/feature/readiness identity assertions; no fallback to legacy partial writes.
- \`alpha_hunter/storage.py\`: optional \`atomic_core_scan_writes=True\` call with explicit PostgREST \`Prefer: return=representation\` to require a JSON commit receipt. Flag is **off** by default.
- \`ops/sql/strategy_payoff_percentile_hotpath_index_candidate_v01.sql\`: uninstalled partial covering index matching observed percentile filter, proposed \`CREATE INDEX CONCURRENTLY\` (outside transaction, only after DBA gate).
- Synthetic PostgreSQL 17 CI: 37 Python tests passed; 50-symbol atomic rollback and complete persistence; replay idempotence; malformed feature and readiness rejection; simulated service_role invocation with RLS enabled, no anon/authenticated RPC EXECUTE. Latest benchmark [run 42362122063](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42362122063) passed.
- 495k-row **synthetic** repeated 50-query benchmark (not real production triggers): baseline 1003.39ms total / p95=24.28ms per query; candidate 511.39ms total / p95=12.72ms; selected outcome count identical (24,574). About 49% aggregate improvement in this synthetic fixture. No guarantee about real scan latency.
- **Not complete end-to-end:** candidate atomic RPC covers five core families only. The Python caller writes additional paper lifecycle records *after* the core RPC. Trigger-created strategies, shadow quotes, freezes, payoff health and paper-order/ledger records also require exact invariants; a successful core receipt is necessary but insufficient for a whole-scan success claim.
- No independent DBA/security approval, private full-schema workload replica, controlled canary or successful repaired production scan has been obtained. A production SQL check confirmed both candidate RPC and index are absent.

## D. Professional execution plan (strict sequential release gates)

### P0 — Immediate containment and observability (safe/read-only; no new credentials)
**Owner:** Engineering + operations.
1. Keep protected scanner, deployed branch, database schema and real-order kill switch unchanged. Keep the new PR draft; never run SQL from the candidate directly on live.
2. Execute the read-only five-family persistence gate for each newly observed scan and label every scan \`CORE_PASS\` / \`CORE_FAIL\` in the operations ledger. Do not publish incomplete data as verified fresh signals; isolate it in reporting without rewriting historical records.
3. Correlate scanner request IDs/run_ids with PostgREST and PostgreSQL timeout log timestamps; collect the exact failing stage (parent/symbol/signal/feature/readiness) and per-attempt elapsed time. Redact secrets and market payloads.
**EXIT:** reproducible read-only incident table and trace chain; no production mutation. Current 13/50 failures establish the baseline.

### P1 — Private production-faithful trigger validation (HARD BLOCKER)
**Owner:** Independent DBA + engineering.
1. Create an **offline, isolated, no-network PostgreSQL 17** environment using existing £0 Codespace/Docker. **Never clone production data into public GitHub or logs.** Full schema export is currently blocked by unknown PostgreSQL password. Don't reset production credentials to solve this. Explore authorised secret-free catalogue introspection for reference metadata and migration history, and secure local-only import with proper credentials if available.
2. Reconstruct private full table DDL, 12 immediate trigger definitions and **all transitive dependencies**, function bodies, indexes, grants, extensions, side-effect tables, exact ordering and security definer context. Compare live MD5 function and trigger definitions immediately before tests and release. Supabase-managed subsystems may require private stubs; every stub must be declared as a deviation, not represented as faithful.
3. Populate sanitized representative volumes (~477k outcome rows), historical skew and 30/50/**61** symbols; benchmark under representative concurrency without external network access. Inspect p50/p95/p99 request wall time, per-trigger latency, Postgres buffer reads, lock waits, WAL/CPU/disk; capture baseline vs candidate.
4. Inject actual-style timeout at symbol 1, 30 and 61; during trigger-created downstream data, before/after feature enrichment, readiness and RPC response loss. Verify full rollback, identical-content safe replay and no duplicate side effects (shadow quote, freeze, geometry health, paper order, ledger).
**EXIT PASS:** confidential DBA evidence packet reproduces all relevant trigger dependencies, test workloads, validated immutable row/hash/side-effect invariants, bounded latency vs 15s client deadline, no missing children or duplicate side effects. An incomplete clone is NO-GO.

### P2 — Performance fix and atomic-writer hardening (isolated only)
**Owner:** Engineering under DBA direction.
1. Compare candidate partial index against representative baseline and explain plans; establish whether it actually removes the slow path. \`CREATE INDEX CONCURRENTLY\` cannot run inside a migration transaction; measure build overhead and rollback procedure.
2. If p99 is still above the deadline, avoid merely increasing client timeout. Consider moving percentile aggregation out of row-trigger critical path to a deterministic **precomputed/as-of cache or downstream observer**, preserving historical cutoff semantics and paper-only trading safety. That architecture requires a separate reviewed migration.
3. Verify effective role-specific statement timeout, PostgREST timeout, HTTP deadline and retry budget; eliminate retries that produce conflict UPDATE trigger side effects. Confirm no unsafe fallbacks from failed atomic RPC.
4. Address end-to-end scan integrity: paper lifecycle writes occur after the five-family atomic receipt. Define deterministic expected keys/counts per scan, idempotent recovery and separate downstream gate.
**EXIT PASS:** full-graph isolated 30/50/61 test at a conservative p99 target **<12s**, plus zero failed/inconsistent writes, zero duplicated downstream effects and source data contract preserved. The target is a proposed acceptance SLO, not measured production performance.

### P3 — Independent DBA + separate security certification (HARD BLOCKER)
**Owners:** Qualified independent DBA and separate security reviewer.
- DBA: review exact commit SHA, dependency graph and fingerprints, latency under full trigger load, index lock/storage impact, backup and rollback, evidence completeness and all shadow/paper side effects.
- Security: review \`SECURITY DEFINER\` trigger chains, \`SECURITY INVOKER\` RPC, RLS/grants, least privilege, source custody, injection/spoofed run identity, replay and no real-order permissions. Confirm anon/authenticated cannot execute RPC.
- Each signs a dated PASS/FAIL attestation against the **same immutable candidate commit and environment fingerprint**. No claim of independent approval from assistant or synthetic CI.
**EXIT PASS:** both qualified signatures present and checked. If reviewers are unavailable, production stays NO-GO, regardless of green tests.

### P4 — Controlled production deployment (only after P1–P3 PASS)
**Owner:** Release manager / authorised operator.
1. Preflight: new schema/trigger fingerprint equals reviewed version, backups/restoration route checked, no unpaid resource required, live scanner remains protected, real orders disabled.
2. DBA-approved candidate index build in controlled maintenance window outside transaction; monitor locks, CPU, WAL, available disk, build status. Verify query-plan improvement and create abort thresholds.
3. Deploy RPC with revoked PUBLIC/anon/authenticated EXECUTE and service_role-only grant; verify function and grants against precise approved migration. Do not enable scanner flag yet.
4. Perform explicitly authorised single isolated canary through the repaired persistence path using only valid paper-safe scan evidence, with no real trading. Validate parent, all child identities/row counts and all trigger side effects; compare commit receipt and live SQL before promotion.
5. Only if canary PASS, promote verified client feature gate in a **web/scanner release path explicitly authorised** for this change, preserving protected P0 continuity and instant rollback. No unrelated UI/repository/trading changes.
**ABORT/ROLLBACK:** timeout, incorrect count/hash, duplicate paper side effect, permission anomaly, live-order path, wrong schema fingerprint, or resource thresholds exceeded. Immediately disable new feature path/restore last approved scanner release and preserve evidence. Index removal, if required, via reviewed \`DROP INDEX CONCURRENTLY\`; do not blindly drop RPC/functions or mutate historical records.

### P5 — Evidence-based post-release certification
**Owner:** Operations + DBA.
- Controlled canary demonstrates an independently verified unique **new run_id** and all five core families, all feature/signal identities, downstream lifecycle and immutable source evidence.
- At least **10 consecutive new scans** with \`CORE_PASS\` and zero missing, duplicate or orphan rows; size coverage to include a heavy 50+ symbol scan and check max 61 capacity in isolated QA.
- 24-hour observation window with zero statement-timeout events attributable to scan writes, acceptable performance and no trading permission change. Historical failures remain explicitly recorded.
- Release packet includes measured p50/p95/p99, unique release SHA, SQL fingerprints, reviewer signatures, rollback proof, post-release checks and a final \`PRODUCTION_READY\` / \`ROLLBACK\` decision.
**EXIT:** only after all these conditions may engineering mark the incident **production repaired**. A single pass or synthetic CI run is not sufficient.

## E. Explicit blockers / next execution

| Priority | Immediate executable work | Blocker | GO condition |
|---|---|---|---|
| 1 | Instrument exact stage, run_id and timeout correlation in isolated code; read-only live baseline | None; £0 | No scans silently pass |
| 2 | Secure representative full-graph private replica and compare live function hashes | Actual schema/trigger custody and private data access | No omitted material trigger |
| 3 | Benchmark/index + atomic RPC under 30/50/61 workloads and failure injection | P1 | p99 under approved deadline; exact persistence |
| 4 | Separate DBA and security signoff against immutable SHA | Independent reviewers unavailable currently | Both signed PASS |
| 5 | Canary, controlled rollout, 10 scans/24h verification | P1–P4 | All core + downstream evidence complete |

**Do not mistake:** synthetic benchmark improvement ≠ verified production performance; operational \`ACTIVE_HEALTHY\` project ≠ complete evidence; parent \`error_count=0\` ≠ persistent scan; green CI ≠ independent review; improving write speed ≠ proving all paper and trigger side effects.

## F. Evidence links and commands

- [Draft repair PR #445](https://github.com/lopushniakoleksij-png/Alpha-Hunter/pull/445)
- [Successful isolated CI and 50-query benchmark](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42362122063)
- [Read-only live five-family persistence gate](../ops/sql/readonly_core_scan_persistence_gate_v01.sql)
- [Read-only trigger/function checksum inventory](../ops/sql/readonly_core_scan_trigger_inventory_v01.sql)
- [Atomic RPC candidate](../ops/sql/atomic_core_scan_rpc_candidate_v01.sql)
- [Partial index candidate](../ops/sql/strategy_payoff_percentile_hotpath_index_candidate_v01.sql)
- [Detailed original release gate](atomic-core-scan-release-gate-20261107.md)

**Status on completion of this audit:** AUDIT COMPLETE; PRODUCTION REMAINS NO-GO; no production change executed.
