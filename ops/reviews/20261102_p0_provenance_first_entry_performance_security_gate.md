# Alpha Hunter P0 — Independent source, first-entry, database load, security review
Date: 2 November 2026 UTC. **RESEARCH / READ ONLY / PRODUCTION NO-GO.**

## Observed production evidence (authoritative direct SELECT, not simulated)
- RENDER_CRON 10:23:28 UTC parent run \`2bcc94bb2853e1763679ac287db71ea5\`: 62 claimed children, 0 child rows, 0 paper exit receipts. The 10:04:41 parent also has 61 claimed / 0 persisted / 0 receipts; the 09:43 and 09:23 records also fail this way. A successful earlier 09:05 scan had 61/61 children and 3 receipts. Do not override the fail-closed live dashboard.
- 147 paper exit-attempt receipts observed since 1 Nov 00:00 UTC all reference existing parent run IDs; **none** references a parent marked \`_canonical_publication_state='VERIFIED'\`. 129 reference parents whose \`validation_identity.run_source\` = RENDER_CRON; others need provenance investigation. This is a legacy data-contract mismatch, **not proof of independently authenticated source custody**.
- 84 recent receipts have producer metadata quote_source=\`BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE\`; 63 lack that metadata. All 147 mark \`captured_quote_only=true\`. The database holds quote fields but does not independently certify provider response, bid/ask top-depth timeliness, external fillability, signature/delivery or market microstructure at stop-touch.
- Three managed paper positions (two SOONUSDT SHORT, one NIGHTUSDT SHORT) have recorded two protective legs and entry source run IDs (which exist), but all have \`unresolved_protective_evidence=true\`. First entry source parents are legacy UNMARKED; first-entry baseline is NOT approved by having two synthetic paper protective IDs.

## Implemented successor research-only evidence contract
Files: \`ops/reviews/phase2_source_custody_and_baseline_v01.py\` and \`tests/test_phase2_source_custody_and_baseline_v01.py\`.

1. \`attest_previous_source\` requires previous receipt source_run_id exactly match a VERIFIED parent; parent source and runtime role both RENDER_CRON; explicit *frozen scientific fingerprint* match; full exact parent/child symbol census; matching symbol/run/payload; timezone-aware observation plausibility; paper-only authority. It returns **DB_CUSTODY_LINKED_NOT_INDEPENDENTLY_AUTHENTICATED** even when all internal checks pass. Historical unmarked receipts fail.
2. \`assess_first_entry_baseline\` separately requires source-linked entry record, matching entry fill run and quantity evidence, both recorded protective legs, no \`unresolved_protective_evidence\`, no horizon failure, same position ID, and first observation within 35m after completed entry. Even a fully internally consistent record remains **CANDIDATE_NEEDS_INDEPENDENT_PROVIDER_AND_PROTECTION_ATTESTATION**. Baseline authorization always FALSE. Legacy managed positions with \`unresolved_protective_evidence=true\` fail.
3. These functions are offline research-only. **Not wired into the active production scanner or the #378 runtime publication path.** Do not change/retroactively reclassify old R8/R9/R10 records. No paper admissions reopen.

## Database performance evidence and proposed benchmark
- Current storage estimate: \`alpha_hunter_symbol_snapshots\` ~1,924 MB/203,493 estimated live tuples; \`alpha_hunter_strategy_observations_v01\` ~3,612 MB/1,640,424 tuples; \`alpha_hunter_strategy_forward_outcomes_v01\` ~213 MB/453,263 tuples; exit-attempt ledger ~11 MB/18,078 tuples. These are PostgreSQL estimates, not exhaustive verified row counts.
- \`pg_stat_statements\` accumulated child PostgREST upsert: 2,568 calls; mean 4,771.8 ms; maximum 11,881.2 ms; cumulative 12,253,930.7 ms. Query performance is severe relative to service_role timeout; not exclusive root-cause proof.
- Read-only \`EXPLAIN\` on the recent previous-receipt query used \`idx_ah_paper_exit_attempt_run_v04\`, with index time filter and subsequent sorting, estimated cost ~245. **This is a plan estimate, not an ANALYZE latency benchmark.**
- Synthetic index study in unmerged #375 passed PG16/17 value parity and rollback, but *not* a full 1.9GB+3.6GB representative nested-write throughput test.
- **Must still run** production-volume, production-like *isolated* PG16/17 PostgREST 61-symbol x relevant 10-strategy trigger chain with full realistically distributed source and cutoff data, concurrent users, cold/warm p50/p95/p99, 57014, locks, WAL, temp file growth, disk pressure, index build/rollback and protected-position receipt latency. Without isolated resource capacity and independent DBA assessment, leave this gate BLOCKED. Do NOT run \`EXPLAIN ANALYZE\` of expensive write paths against production.

## Security review — independent approval NOT granted
- \`public.alpha_hunter_snapshots\` and \`public.alpha_hunter_symbol_snapshots\` currently have RLS ON and **zero policies**, but SQL GRANT metadata gives anon/authenticated underlying SELECT/INSERT rights. Effective access is constrained by RLS; do not conflate metadata grants with exposure.
- \`public.alpha_hunter_paper_exit_attempts_v04\` RLS ON, zero policies, and anon/authenticated have no SELECT/INSERT grants. \`alpha_hunter_paper_protection_horizon_open_v09\` has \`security_invoker=true,security_barrier=true\`, and no anon/authenticated SELECT grant.
- Supabase advisor: 128 informational \`rls_enabled_no_policy\` findings, 34 informational \`unindexed_foreign_keys\`, 76 \`unused_index\` and one \`auth_db_connections_absolute\`. They require risk-based review, not automatic application. Advisor is NOT independent penetration testing.
- Before any release, test actual unauthenticated, authenticated and service-role access in **isolated staging**; ensure no direct quote/position write from public client, no SECURITY DEFINER RPC exposure, and correct schema/credential placement, role grants, RLS, production secret custody.
- Review relevant guidance: https://supabase.com/docs/guides/database/views and https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy.

## Controlled release gate
1. Preserve main scanner cron \`crn-d9nmbjbm8hqs73elu6hg\` which auto-deploys from \`main\`; web autoDeploy is off. No generic merge or unattended branch checkout into cron; do not disable cron or change its schedule.
2. Independent signed DBA, security, scientific and operations approval of exact reviewed SHA, migration index and rollback, protected paper positions and alert path.
3. Release code only at an explicit successor isolation boundary with owner authorization and verified noninterference. If isolation cannot be proven with zero new spend, release NO-GO.
4. Observe prospective evidence: exact child counts, verified previous-source parents, independently delivered quote/alert custody, first-entry source baseline, paper protection and frozen 35m continuity. Any mismatch remains UNKNOWN/FAIL, with no backfill.
5. Preserve paper-only, trade_permission=false, R10 admission halt and immutable previous cohort evidence.

**Verdict:** added stricter *offline* source and first-entry evidence classifier; production external provenance / first baseline / full load and security remain NOT VERIFIED. No human DBA or security approval has been issued.
