# ALPHA HUNTER — P0 Database-write repair completion board

**Start reference:** 2026-11-14, audit: `alpha_hunter_database_repair_full_audit_2026-11-14` (owner's detailed 14-Nov review) and the linked GitHub evidence packets.  
**Authorised scope:** existing PR #445 / `fix/supabase-write-timeout-qa`, isolated QA only, read-only investigation of production. **Production NO-GO.** Do not merge/deploy/migrate, restart production, spend, enable real orders, duplicate canonical scanners or change the 2026 scientific seal.

## Already verified — do not redo without a specific regression

- [x] Candidate atomic five-family RPC designed with strict receipt, immutable-run anti-replay and service_role restrictions (design review, NOT live acceptance).
- [x] Private QA single synthetic 61-symbol commit and post-commit retry passed: core `1,61,7,7,61`, no duplicate downstream effects.
- [x] 30 rollback-only RPC samples (p95 44.233ms; not durable/HTTP).
- [x] 30 separate sequential durable QA commits and retries (commit p95 120.610ms; p99/max 121.843ms; same 61-symbol synthetic fixture, not production p99).
- [x] Collector configured Supabase failure now returns nonzero in draft branch only; source and synthetic regression tests passed.
- [x] 2026-11-14 exact-head GitHub suite 1,460 tests + 101 subtests and all 11 queried workflows PASS; PR remains draft/unmerged.
- [x] Production read-only audit revealed recurring parent-only partial persistence: 38/50 core-shape match, 12/50 parent-only; latest 12/12 pass. Recorded Render SQLSTATE 57014 / client timeouts. Candidate RPC not installed in production.

All checked items above are **evidence-limited** to their stated scope.

## Gate A — preserve and restore the private Codespaces QA reference (P0 blocker)

- [ ] A1. Collect sanitized `docker inspect` state, exit reason, started/finished timestamps, mount types/count, recent historical container events and final-window log classification. Last observed exit: `255`, `OOMKilled=false`, no unambiguous origin.
- [ ] A2. Record verified private backup/archive identity, SHA-256, permissions and offline custody. Do not send SQL or secrets to public GitHub or chat.
- [ ] A3. Establish stopped-container cause to the extent possible; distinguish Codespace/Docker lifecycle, PostgreSQL startup, permission, storage and memory hypotheses. A `255` code is **not proof** of corruption or safe restart.
- [ ] A4. Authorise safe start of the **same container only** after mounts/backup/identity checks. Preserve network `none`, same image/process and no auto-restart.
- [ ] A5. Verify catalog/cron target, trigger graph, zero scheduled jobs, reference integrity and recovery evidence; record sanitized results.
**Exit:** DBA/engineering witness accepts documented QA baseline recovery; no deleted container/reference data.

## Gate B — production-equivalent schema and security parity

- [ ] B1. Obtain/verify the authorised **private** schema-only archive; never expose trigger bodies/secret data in PR.
- [ ] B2. Compare extension versions, full nested trigger DAG, callback owners/security-definer flags, indexes, RLS, grants, namespaces and `pg_cron` view dependencies against live read-only metadata. Record stable fingerprints.
- [ ] B3. Resolve all mismatches or mark the test NOT EQUIVALENT; require independent DBA sign-off for exact candidate SHA.
**Exit:** signed private schema-parity certificate.

## Gate C — correctness under concurrency and failure

- [ ] C1. Same-run 3-client truly simultaneous durable commit; require all receipts and one exact five-family result, once-only downstream side effects and clean replay.
- [ ] C2. Different-run overlapping writers and maximum expected symbol population; no lock starvation, unacceptable wait or cross-run contamination.
- [ ] C3. Immutable conflicting retries must fail without changing existing evidence.
- [ ] C4. Inject statement timeout/HTTP read timeout/lost acknowledgement/cancellation/deadlock/rollback at each core write and nested trigger stage; verify zero partial parent-only commits and no orphan/cross-run effects.
- [ ] C5. Verify separately persisted paper-lifecycle decisions, orders, fills, protections, outcome records, quote/freeze and payoff/strategy side effects. Five-family atomicity alone is **not** full end-to-end atomicity.
- [ ] C6. Verify strict fail-closed service-role behaviour for insufficient privileges, unexpected HTTP statuses and missing/malformed receipts; no REST fallback; real orders remain disabled.
**Exit:** immutable test evidence bundle, exact SHA, no unexplained blocked tests.

## Gate D — performance, query-plan and capacity acceptance

- [ ] D1. Durable serial and concurrent tests for 30/50/61 and observed peak sizes; include varied payload/trigger paths, not only repeat of one fixture.
- [ ] D2. Actual PostgREST `service_role` HTTP p50/p95/p99, configured 15s client timeout and SQL statement timeout, response/lost-ack handling; include realistic stress/peak conditions.
- [ ] D3. Observe WAL, locks, buffers, slow nested functions and transaction duration, and replay side-effect counts.
- [ ] D4. A/B the optional payoff-percentile partial index on equivalent QA data; compare execution plans/latency and write amplification; signed DBA install-or-reject decision.
**Exit:** acceptance thresholds set *before* test, achieved with margin, and signed by DBA. A 30-sample p99=max is not a production SLO.

## Gate E — canonical writer, failure semantics and monitoring

- [ ] E1. Independently bind production incomplete parents to Render/GitHub authenticated job IDs, commits and timestamp windows; self-reported `validation_identity` alone is not proof of publisher identity.
- [ ] E2. Verify obsolete writers cannot submit parent-only scans; preserve one canonical scanner and existing schedules.
- [ ] E3. On a failed configured Supabase write, verify the collector returns nonzero **end-to-end**, cron reports failed, an alert fires, and the existing scanner can continue on the next scheduled run.
- [ ] E4. Define immutable per-run completion ledger and alert for parent-only, readiness-missing, orphan/duplicate and old-format publisher regressions. Preserve historical failures.
**Exit:** source custody and failure-reporting witnesses pass in protected rehearsal.

## Gate F — independent release authorisation and controlled paper-only verification

- [ ] F1. Separate independent **DBA** and **security** approvals for one frozen SHA, private evidence, privileges and trading boundaries.
- [ ] F2. Ops checklist: exact code/schema release sequence, snapshot/rollback, owner-approved no-cost window, stop conditions and no live trading.
- [ ] F3. Owner explicitly approves migration/deployment; until then **no production changes**.
- [ ] F4. Controlled paper-only canary: verify new scan parent, all four child families, all downstream evidence and source lineage. Stop and roll back upon any mismatch.
- [ ] F5. Run signed acceptance observation window covering peak load, no partial or false-success scans. Publish dated certification and close P0 only after gate owners accept all evidence.
**Exit:** release GO signed, evidence archived private, current PR no longer blocked.

## Next single action

**A1:** Run the *read-only* isolated QA exit-255 diagnostic in the existing Codespace; do not restart or delete the container. Move to A2 only after returning the sanitized status. All other gates retain `BLOCKED` dependencies on A1/B2.

## Traceability

- Repair PR: https://github.com/lopushniakoleksij-png/Alpha-Hunter/pull/445
- Stage 7/8 durable evidence: `docs/P0_STAGE7_ISOLATED_COMMITTED_61_PROBE_EVIDENCE_20261111.md`
- Production 14-Nov evidence: `docs/P0_PRODUCTION_READONLY_PERSISTENCE_EVIDENCE_20261114.md`
- Existing release gate: `docs/atomic-core-scan-release-gate-20261107.md`

**Management discipline:** no "90% complete" claim, no independent signoff inferred from GitHub CI, and no proof of fixed production persistence until a permitted released canary completes.
