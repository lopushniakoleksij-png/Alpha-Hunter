# ALPHA HUNTER — P0 Isolated HTTP Performance and Production Trigger-Graph Candidates
Date: 2026-11-05 (Europe/London)  
Decision: **PRODUCTION NO-GO / PR #418 DRAFT ONLY / NO DEPLOY**.

## Production dependency graph — READ ONLY, NOT AN EXACT REPLAY

Catalog inspection on existing production PostgreSQL 17.6 without writing:

- Five seed canonical tables; recursive lexical relation references from enabled PostgreSQL trigger function definitions, with cycle suppression and depth limit six.
- **22 candidate tables**, **31 attached enabled triggers** (15 include INSERT; 16 do not), **26 possible relation-reference edges**, and maximum discovered depth four.
- **13 triggers use SECURITY DEFINER**. This is a privileged execution-path concern for reviewers, **not** proof every one executes during a scan.
- Candidate paths include snapshot -> account-state/position materialisation, symbol -> strategy episodes/observations -> shadow quote -> execution-decision freeze -> calibrated paper-order logic. Trigger branches may not run in the actual scan; read-only SELECT references are not necessarily writes. Nested function calls, dynamic SQL and dependencies outside the naming pattern may be missing.
- The graph manifest is `ops/reviews/p0_production_trigger_dependency_candidates_20261105.json`. The seven first-order hooks remain fingerprinted separately in `ops/reviews/p0_readonly_production_fingerprints_20261105.json`.
- Production schema and security have not been changed. No trigger source bodies, secrets or production user rows were put in this GitHub repository.

**Required next acceptance:** qualified DBA independently identify exact transitive executed SQL/trigger graph in a private sanitized clone, including all tables, indexes, constraints, RLS, security-definer owner/search_path and feature flags. Candidate manifest alone is NOT acceptance.

## Synthetic local PostgREST HTTP benchmark — measured, NOT production-equivalent

GitHub Actions isolated execution: https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42003208610  
Tested source commit: `7fa50ed23d5b8b279bef76dc50cdbaed67067f31`  
PostgREST 12.2.8 / disposable PostgreSQL 16.15 and 17.11. No actual Supabase gateway, production trigger bodies, database load, network latency or live credentials. For each 61/62/63-symbol group: two warmups and **30 actual HTTP atomic POST samples**; one parent + one signal/feature/readiness/child per symbol, ten **synthetic** observations per symbol. Unchanged scientific/trading permissions: false.

| PostgreSQL | Symbols | Samples | p50 HTTP ms | p95 HTTP ms | p99 HTTP ms | Maximum ms |
|---|---:|---:|---:|---:|---:|---:|
| 16.15 | 61 | 30 | 22.087 | 26.528 | 81.775 | 103.360 |
| 16.15 | 62 | 30 | 22.245 | 23.625 | 77.743 | 99.656 |
| 16.15 | 63 | 30 | 23.149 | 24.562 | 24.963 | 25.094 |
| 17.11 | 61 | 30 | 19.369 | 28.865 | 78.962 | 98.550 |
| 17.11 | 62 | 30 | 19.096 | 21.331 | 77.400 | 100.269 |
| 17.11 | 63 | 30 | 20.744 | 29.716 | 36.677 | 37.399 |

- Percentiles are linear interpolation over **30 samples** per group; they are descriptive, not reliable tail-latency guarantees. Synthetic fixture has simplified schema/triggers, no actual production indexes/data volumes, and no per-trigger timer. **Never claim these latencies represent the 4.8-second production insert mean.**
- Eight concurrent **distinct-run** HTTP posts across four workers: PostgreSQL 16 p95 72.037 ms, maximum 72.169 ms; PostgreSQL 17 p95 57.492 ms, maximum 63.701 ms (again fixture only).
- Simultaneous **duplicate-run** requests: one HTTP 200 and one HTTP 409 on each database. Exactly one full five-stage publication persisted. No doubled run and zero enabled trade permission.
- Earlier isolated fault matrix still passed: rollback on child/feature errors, malformed counts, identity checks, forged trading flags, simulated lost ACK with readback and signed JWT denial/positive role checks.
- Production trigger p50/p95/p99, authenticated Supabase gateway grants, disk/WAL/lock costs, security-definer side effects and 15s timeout compliance remain **NOT TESTED** on an exact replica.
- GitHub CI names containing “Production” refer to test suites, not production database tests.

## Evidence chain and pending independent decision

- Publication and replay integrity: isolated CI **PASS**, not exact-schema acceptance.
- Candidate graph catalog metadata: captured **PASS**, not verified executable closure.
- Real production-style trigger p50/p95/p99 at realistic data volume and contention: **BLOCKED** until private isolated clone.
- Effective permissions on local PostgREST test service: **PASS**; real Supabase auth, function grants, SECURITY DEFINER chain: **BLOCKED**.
- DBA, independent security, source-custody, paper-risk, operations reviewer signatures: **NONE ON RECORD**.
- Owner authorisation to touch scanner: **NOT GIVEN**.

**No production writes/DDL, production scanner/cron/Render changes, new cloud resources, trading permission changes or merge to main.**
