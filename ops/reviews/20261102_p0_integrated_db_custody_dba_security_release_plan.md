# P0 integrated snapshot/custody repair — DBA, security, and controlled-release review
Date: 2026-11-02 UTC. Status: DRAFT / NOT RELEASE-AUTHORIZED.

## Scope and source identities
- Parent candidate: draft #371, head `5024226a1897ea87ab8e6ec5ec50847c6f7989eb`, **NOT** production.
- #371 already includes eight-child bounded writes (the same batch-size idea as #372), PENDING -> VERIFIED parent state, full child readback, pre-exit inventory and real local PostgREST receipt checks. Do **not** blindly merge #372 and produce conflicting file writes.
- **Successor runtime change on this stacked #378 branch:** the canonical writer now independently queries prior durable `alpha_hunter_paper_exit_attempts_v04` rows from another run and enforces the previous-to-current <=35-minute bound before promoting PENDING to VERIFIED. It fails closed if preceding evidence is absent, malformed, too old, duplicated, or has invalid identity/outcome/authority. The unchanged #371 base alone does NOT contain this runtime continuity enforcement. The separate #377 gate additionally checks successor fingerprint and exit-side capacity; that pure classifier is NOT yet wired into the producer.
- #375 proposes a narrow PostgreSQL partial index for repeated downstream percentile aggregation in the AFTER symbol trigger. Its successful isolated SQL parity/rollback does not prove that true nested trigger latency at realistic load is acceptable. Its SQL is non-auto-executable and **must not be applied to production without DBA approval**.

## Reproduced production P0 evidence (read-only)
2 Nov 2026: RENDER_CRON 09:05:53 run 61/61 child rows and 3 same-run paper exit-attempt receipts; 09:23:21 and 09:43:22 claimed 61 children each, persisted 0 children and 0 matching position receipts. A blank child set cannot be treated as empty success or filled retrospectively.

## Isolated integrated acceptance
Workflow: `.github/workflows/phase2-integrated-postgrest-20261102.yml`, PG16 and PG17, PostgREST v12.2.8, no live credentials.
1. Create 61 synthetic children with deterministic run/symbol identities and a real AFTER-trigger chain that executes a representative percentile calculation.
2. Trigger nested SQLSTATE 57014 on TEST032USDT. Actual local HTTP upsert fails after four 8-row batches: parent remains PENDING; exactly 32 children persist; zero same-run receipts.
3. Drop the *test-only* failure trigger. Retrying same deterministic run must preserve idempotent children. Even with 61 children, absent current-run receipt leaves PENDING.
4. Insert one synthetic current-run paper receipt into isolated PostgreSQL. Then verify parent publication to VERIFIED, 61/61 children, one matching current-run receipt.
5. Runtime publication itself stays PENDING if a current receipt has no prior real DB observation or has a prior observation >35m earlier; it becomes VERIFIED only after an independently stored <=35m prior receipt. The separate scientific replay still preserves the invalid 40-minute historical gap; trade permission remains FALSE.
6. All legacy/initial 57014, lost ACK, missing receipt, concurrent position removal and identity tests in #371 must still pass.

## Independent DBA review — explicitly NOT APPROVED
- Review EXPLAIN (ANALYZE, BUFFERS), statement timeout, locks, WAL, partial index size, write amplification, trigger fanout, table/TOAST growth, per-batch p50/p95/p99.
- Reproduce the precise nested production trigger chain with representative *synthetic* volume on PostgreSQL 16/17 and PostgREST, including concurrent writes. The current simplified trigger is a structural failure test, NOT workload equivalence.
- Compare #371 eight-row writer with #372; select one idempotent write implementation, no retries that duplicate downstream trigger effects. Classify any uncertain commit as UNKNOWN until exact readback.
- Benchmark #375 index candidate with representative statistics and space, ensure aggregate parity, and validate isolated CREATE/DROP INDEX CONCURRENTLY outside transactions; identify lock and rollback risk.
- Explicitly prevent full-scan success based on parent count alone. Only immutable same-run child/receipt identity evidence can certify publication. Reject stale age and gaps from *previous* position observation.
- Independent named DBA reviewer and documented approval required before any production DB/index change.

## Security / risk review — NOT APPROVED
- Review no broad grants, RLS bypass, definer code, exposed RPC, auth secrets, service_role in browser, unrestricted public read of position or quote receipts.
- Read-only verifiers must not have write privileges; do not store credentials in CI logs; no Bitget order or transfer methods.
- Verify all-ledger paper residuals, not solely managed horizon-open view; missing quote-source attestation, partial-fill/residual OCO handling, closed-position transient custody and alert delivery must be separately reviewed.
- Preserve immutable R8–R10 evidence, scientific fingerprints and deadlines, original losses, <=35m maximum, and R10 admission halt.
- Independent security/science/risk reviewers with recorded approval required.

## Controlled deployment procedure — PROPOSED ONLY, NOT EXECUTED
0. Freeze exact proposed SHA, test matrix, verified release diff, and approved rollback image/commit. Confirm Render cron autoDeploy/main interaction, current service IDs, current production cron and paper position protections via read-only checks.
1. Never merge an unapproved research or web PR to main while P0 cron auto-deploys. Establish reviewed branch/service isolation without adding spend; if impossible, release is BLOCKED.
2. Obtain DBA/security/risk/science/release signoffs and separate owner authorization. Keep new admissions halted, real orders disabled, original protocol records untouched.
3. If index is independently authorized, apply only approved `CREATE INDEX CONCURRENTLY` in a separately controlled production change. Record before/after query plan, lock and WAL telemetry; stop on regression and apply reviewed `DROP INDEX CONCURRENTLY` rollback. **Not part of this PR.**
4. Controlled successor release of integrated write/publication/custody code must be isolated from still-running R9/R10 protections, or postponed. No old cohort rewrites, no cron double-run, no synthetic backfill.
5. Canary *future* independent observation cycles: verify parent PENDING->VERIFIED, exact children, same-run position receipts, previous gap <=35m, independently sourced quotes and durable delivered alerts. Retain negative intervals and no false PASS.
6. If any operation produces partial children, stale receipt, fingerprint mismatch, timeout, ambiguous ACK, missing protective evidence or duplicated writer, rollback successor to prior verified commit while preserving existing monitor/protection path and recording the failed attempt. No retrospective fabricated pass.

## Verdict
Successor runtime continuity **implemented and PG16/PG17 PostgREST-tested at an isolated draft SHA**. No old science is reclassified. Production NO-GO pending full trigger-load equivalence, cross-run receipt provenance, all-ledger scientific custody, independent DBA/security signoff and release isolation. This is not live profit proof or a deployed repair.
