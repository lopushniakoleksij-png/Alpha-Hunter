# Alpha Hunter P0 — Expanded trigger, role and rollback DBA acceptance record

Date: 2 November 2026 UTC. Status: **ISOLATED ENGINEERING PASS; INDEPENDENT RELEASE APPROVAL NO-GO**.

## Source anchors

- Stacked draft PR #378 on an unmerged publication branch, never main.
- Isolated full-width parent/protection benchmark GitHub Actions run 41443589407 at SHA c5e87e9939b1c5caa6fc54fa9a184fd3c3be0a7b.
- Actual PostgREST anonymous/authenticated/writer RLS actor checks PG16/17 run 41443589337 at the same SHA.
- Parent/ledger/protection + payoff/calibration fail-closed and transaction rollback PG16/17 run 41443970017 at SHA f18b2096fc407b68a6a551694a7665cd530a5ca8.
- Separate real PostgREST SQLSTATE 57014 and ambiguous ACK tests PG16/17 run 41441823356.
- Catalog-derived schema files in tests/fixtures/p0_production_catalog_trigger_chain_20261102.sql and tests/fixtures/p0_catalog_parent_ledger_protection_addendum_20261102.sql. Empty synthetic tables and exact catalog-derived functions only, no historic trading records, credentials or production mutations.

## Actual extended PostgreSQL 16/17 load evidence

Read-only production size samples: symbol JSONB payload average 8,421B / p50 8,707B / p95 9,716B; strategy payload average 1,069B / p50 1,039B / p95 1,333B. Production strategy observations total approximately 3.6GB.

PG16/PG17 benchmark seeded 1,640,424 synthetic historical strategy observations, occupying 3,823,845,376 bytes, with 3 concurrent local PostgREST HTTP clients each writing 62 symbol rows carrying 10 strategies. Verified EXACT 186 children, 1,860 strategy observations, 1,860 episodes, 1,860 24h queue entries, 930 shadow quotes, 3 parent account materialization events, 3 paper-only open positions and 3 protection reconciliation events. All trade_permission false.

PG16: eight-row HTTP p50 63.55ms, p95 640.46ms, maximum 945.61ms. PG17: p50 110.66ms, p95 648.59ms, maximum 692.25ms. These are GitHub disposable container readings, NOT live cloud SLA or sustained p99 guarantees. Synthesized symbol payload p50 8,233.5B, somewhat smaller than real 8,707B.

This expanded benchmark uses 12 catalog-derived production PL/pgSQL functions, table column types, constraints, indexes and synthetic account-position inputs. The primary market/strategy/shadow quote/episode/24h queue and account ledger/position/protection paths have been exercised. Frozen execution/activation interlock dependencies, real cost-floor view, actual production RLS/service role and all workload/lock/write-amplification variants are NOT fully exercised. Full production equivalence remains unproved.

## Protection, payoff, and rollback evidence

- Parent materialization handles missing/not-configured private account and invalid connected-account data fail closed; a synthetic connected account with one open paper position yielded account state and protective reconciliation rows. No exchange call or live order.
- Exact payoff-geometry and calibrated-paper trigger function bodies attached to synthetic decision-freeze insert: active geometry-health spec with no eligible historical outcomes produces INSUFFICIENT_HISTORY; no confidence/profit promotion, and without a calibration policy no synthetic paper orders.
- An empty synthetic cost-floor view was substituted solely to exercise a safe geometry branch. It does NOT verify the actual production cost model or cost-source provenance.
- SQL savepoint rollback left no orphan geometry or account ledger records.
- Separate PostgREST 57014 failure test preserved a PENDING parent and 32 prior children, then exact same-run retry produced 62 children and 620 unique observations. A lost HTTP acknowledgement left one committed child; exact readback/retry retained one child and 10 unique observations. This is not simultaneous full-width fault testing.

## Actual role/security test

PG16/PG17 real local PostgREST JWT role switching passed: synthetic anonymous and authenticated roles could not read sensitive records or insert forged parents/children despite underlying SQL GRANTs; an isolated dedicated writer could insert one parent and trigger its expected fail-closed account materialization. This does NOT reproduce real Supabase service_role BYPASSRLS, gateway proxy, JWT secret custody, role ownership, auth API, SECURITY DEFINER review or independently approved permissions.

## Historical first-entry exceptions

All three managed paper positions (two SOONUSDT shorts, one NIGHTUSDT short) retain two recorded modeled protective legs but first receipts are AMBIGUOUS with ENTRY_AND_EXIT_ORDERING_AMBIGUOUS_SAME_SNAPSHOT. unresolved_protective_evidence remains true. Their exact stop/target ordering is not independently reconstructed. No backfill, trade or scientific promotion is authorised.

## Live production persistence warning

Latest read-only snapshot inspection showed the 2026-11-02 12:05:21 UTC parent still claimed 61 scanned symbols and 0 errors, but had ZERO child rows and ZERO position receipts. Earlier scans intermittently had 61/61/3. The underlying production incident is NOT resolved by isolated green CI.

## Release decision and outstanding signoffs

DBA NOT APPROVED: complete activation/cohort guard and actual cost-floor dependencies, real production indexes/grants, cold/warm sustained multi-concurrency p95/p99, WAL/disk/lock metrics, full-width fault injection and migration/index rollback.

Security NOT APPROVED: actual Supabase public gateway, service_role least privilege and BYPASSRLS, SECURITY DEFINER paths, source quote provenance and durable alert acknowledgement.

Scientific/Risk NOT APPROVED: first-entry protective ordering, independent quote sourcing and 35-minute prior/current monitoring custody; historical R8 invalidation and R10 admission halt remain frozen.

Operations NOT APPROVED: Render protected P0 hourly cron still deploys from main with autoDeploy=yes. Merge to main risks protected scanner. Only an independently approved, separately isolated successor release with immutable SHA, no-interference evidence, owner signoff, a verified canary and rollback could qualify. No new expense is approved.

**Final: local extended trigger/role/fault checks PASS in their bounded scopes; full production-equivalent performance/security and human approvals NOT PASSED; production deployment NO-GO. R9/R10, paper positions and scanner unchanged; £0 spent.**
