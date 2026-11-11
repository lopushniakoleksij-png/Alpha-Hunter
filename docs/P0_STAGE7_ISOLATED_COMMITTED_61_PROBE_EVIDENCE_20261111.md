# Alpha Hunter P0 — Stage 7 isolated committed 61-symbol probe (2026-11-11)

**Status: STAGE 7 SINGLE-COMMIT/RETRY PASS — PRODUCTION NO-GO.**
**Evidence provenance:** Owner-supplied Codespaces terminal screenshot, 2026-11-11 13:12 London / UTC. This report transcribes the visible sanitized console results. It does not represent independent DBA attestation or access to the private test environment from GitHub.

## Test subject and isolation

- Draft PR #445 on `fix/supabase-write-timeout-qa`; the candidate write path is not enabled in production.
- Stage 7 controller: `ops/local/qa_stage7_cron_quiescence_controller_v01.py`.
- Commit/retry probe: `ops/local/qa_stage7_physical_template_61_v01.py`.
- Existing network-isolated PostgreSQL 17 private Codespaces QA container and private reference clone.
- Physical PostgreSQL TEMPLATE clone preserved `pg_cron`, the `cron.job`-dependent Alpha Hunter application view, application trigger graph and permissions in the disposable clone.
- The QA cron launcher was temporarily redirected from the reference database and its original configuration restored after the probe. No production connection or reference-database writes were reported.
- The disposable database was removed after the test.

## Observed terminal evidence

| Console result | Observed value |
| --- | --- |
| `QA_ONLY_GUARDS` | PASS |
| `QA_GUARD_DIAGNOSTIC` | PASS |
| `QA_CRON_LAUNCHER_REDIRECTED` | PASS |
| `STAGE7_PHYSICAL_CLONE_COMMIT` | PASS |
| `COMMITTED_CORE_COUNTS` | 1 parent, 61 symbols, 7 signals, 7 features, 61 readiness |
| `RETRY_NO_DUPLICATES` | PASS |
| `PRIVATE_SNAPSHOT_SIDE_EFFECT` | PASS |
| `CRON_DEPENDENT_VIEW_PRESERVED_BY_TEMPLATE` | PASS |
| `SIDE_EFFECT_COUNT_PRIVATE_ALPHA_HUNTER_SNAPSHOT_SLIM_V01` | 1 |
| `SIDE_EFFECT_COUNT_PUBLIC_ALPHA_HUNTER_ACCOUNT_LEDGER_MATERIALIZATION_EVENTS` | 1 |
| `SIDE_EFFECT_COUNT_PUBLIC_ALPHA_HUNTER_ACCOUNT_STATE_SNAPSHOTS` | 2 |
| `FIRST_TRANSACTION_CLIENT_WALL_MS` | 117.852 |
| `RETRY_TRANSACTION_CLIENT_WALL_MS` | 94.088 |
| `PRODUCTION_CONNECTIONS` | NONE |
| `REFERENCE_DATABASE_WRITES` | NONE |
| `DISPOSABLE_DB_REMOVED` | PASS |
| `QA_PROBE_STATUS` | PASS |
| `QA_ORIGINAL_CRON_CONFIG_RESTORED` | PASS |
| `QA_CRON_CONTROLLER` | PASS |
| `PRODUCTION_RELEASE` | NO_GO |

**Interpretation:** one synthetic, durable five-family commit and an idempotent post-commit retry succeeded in a disposable copy of the private QA reference. These two wall-clock durations are *individual observations*, not p50/p95/p99 statistics. The downstream side-effect totals are the probe's recorded counts, not independent complete lifecycle lineage certification.

## Still open — mandatory acceptance gates

1. Validate and independently attest the private QA reference's full production-equivalent schema, indexes, grants, nested trigger fingerprints and function definitions against the authorised production baseline.
2. Benchmark realistic serial and concurrent **durable committed** workloads across 30/50/61 and peak symbol sizes, measuring p50/p95/p99, locks, WAL, latency tails and configured HTTP/statement timeouts; test rollback and zero-orphan failure injection.
3. Recheck *full* downstream evidence (including strategy, quote/freeze, payoff, paper-order and outcome queue) for correct per-run lineage and zero duplicate side effects.
4. Authenticate/retire the obsolete scan publisher independently from the current writer repair; verify canonical scan source custody and readiness.
5. Obtain separate signed DBA and qualified security approvals for an immutable exact release commit, plus a documented £0 rollout/rollback gate.
6. Only after approval, plan an explicitly authorised controlled paper-only production trial; do not merge, migrate, deploy or enable real orders before that gate.

**Safety boundary:** Do not publish private SQL, production secrets, customer records or database backups in this public repository. No merge, deployment, scanner modification or trading authorization is implied by this report.
