# Alpha Hunter P0 — 23 November 2026 production schema baseline and private QA access gate

**Checkpoint:** approx. 12:02 GMT (UTC), 2026-11-23. **Status: PRODUCTION NO-GO; research/paper-only; no merge, deployment, migration, production database write, scanner restart, trading permission change, or spend.** This is a read-only evidence report, **not** a private PostgreSQL restoration, benchmark, sign-off, or certification.

## A1 — original private QA access remains genuinely blocked

Connected GitHub tools can inspect branch files, PRs, CI, reviews and issue comments, but expose **no Codespaces terminal, Docker client, private filesystem or local PostgreSQL execution**. An optional connected browser profile was inspected read-only and contained **no recorded GitHub signed-in session**, so it does not provide independently authorised Codespaces access. No Codespace was started, stopped, restarted, rebuilt, provisioned, accessed or connected through a tunnel in this checkpoint.

The original private container `alpha-hunter-private-postgres17-qa` state, exit-255 cause, preserved volumes and private schema-only archive cannot be independently reverified. Its protected contents must stay in the owner-authorised private environment, not published to GitHub or this conversation. Do not mistake Stage 7 database `ah_authentic_schema_20261110` for authentic full-parity target `alpha_hunter_private_qa`.

**Next preflight when approved access exists:** existing repository `ops/local/p0_qa_exit255_readonly_diag_v01.py`, then `ops/local/p0_private_qa_identity_readonly_v01.py` and `ops/local/verify_restored_private_pg17_fingerprints_v01.sh`. Do NOT restart the old container before private backup/volume custody and exit-255 assessment. The latter scripts must not run unless the A1 prerequisites are met.

## B2/B3 — current production catalog is STILL equal to the earlier verified baseline

Read-only production Supabase `pg_catalog` SQL from repository files `ops/sql/readonly_stage2_structural_fingerprint_v01.sql` and `ops/sql/readonly_p0_private_function_catalog_fingerprint_v01.sql` was rerun, excluding all private bodies and credentials from output.

| Property | Fresh SELECT-only result 23 Nov |
|---|---|
| Public Alpha Hunter application tables / RLS-enabled | 128 / 128 |
| Columns / indexes / policy rows | 3,012 / 360 / 0 |
| Application row triggers / trigger-bearing tables | 131 / 108 |
| Distinct trigger functions / definer call sites | 36 / 21 |
| Columns fingerprint | `c802a3e3d96d620a20adc8c3af350472` |
| Indexes fingerprint | `5a7e8cbe8b8450677f6be84a77caaa6e` |
| Trigger/function fingerprint | `5c5b202307ef6bb57b4a9b08082c2a1e` |
| Table grants + RLS fingerprint | `c9785c793fa51a732c2edc96ba22c7eb` |
| `private` functions / SECURITY DEFINER / runtime settings | 110 / 65 / 110 |
| `private` full function custody digest | `8fae5afad12f3040d30d0416cbfd9be1` |
| Public `alpha_hunter_%` functions / SECURITY DEFINER / runtime settings | 10 / 5 / 10 |
| Public function custody digest | `a75b1d2ed683766dbd5ffa3830f7f087` |
| Private-schema application triggers | 0 |
| Extension count | 8 |

Extensions (name, version, install schema) confirmed in production read-only: `http 1.6 extensions`, `pg_cron 1.6.4 pg_catalog`, `pg_net 0.20.4 extensions`, `pg_stat_statements 1.11 extensions`, `pgcrypto 1.3 extensions`, `plpgsql 1.0 pg_catalog`, `supabase_vault 0.3.1 vault`, `uuid-ossp 1.1 extensions`.

All these hashes and counts **match the previously recorded 17 November production structural baseline**. This keeps the known fingerprint reference current at this checkpoint, but says nothing about the unavailable restored QA clone's actual contents, physical topology, privileges, runtime settings, dynamic dependencies or full trigger behavior. The saved fingerprint comparison script may still be insufficient to certify full-parity restoration; qualified review is mandatory.

## P0 production persistence severity, read-only provider identity matched

From latest **50 mature parent scans** (at least 5 minutes after collected timestamp), **23/50** matched core family-count shape and **27/50** were **PARENT_ONLY** (declared symbols > 0 but 0 stored symbol, signal, feature and readiness children); no other partial-count cases in this sample. Latest **12** parent scans: **1/12** matching core shape, **11/12 PARENT_ONLY**. Latest parent-only: **11:43:30.86674 UTC** on 23 Nov. Rolling counts are not a complete-window loss rate. A matching five-family count is **not** full semantic/side-effect certification.

Original authenticated Render cron application logs 10:00–12:02 UTC directly linked **six precise run IDs**, checked again with Supabase `SELECT` by the same IDs, not self-declared publisher JSON:

| Render time UTC | Exact run ID | Application result | Declared symbols / each child family |
|---|---|---|---|
| 10:06 | `5f1ad200b2e31a8bac5e88516f2b6f2b` | HTTP 500 PostgreSQL `57014` | 58 / 0 |
| 10:24 | `96334c3fd8822fcdd75627eb084f9882` | `SAVED` | 60 / 60 |
| 10:44 | `0f2f3ec4e5c284745e8246e32d8b3ec6` | HTTP 500 PostgreSQL `57014` | 58 / 0 |
| 11:06 | `37e365b46e6d77bb0a8c9055b237a789` | HTTP 500 PostgreSQL `57014` | 60 / 0 |
| 11:24 | `2239dd38bd5c45fb6b96474cb8f2b7fb` | HTTP read timeout, 15s per retry | 61 / 0 |
| 11:44 | `30ba730738813cf56880dbf94976a26b` | HTTP read timeout, 15s per retry | 61 / 0 |

Five failures (3 server-side 57014, 2 client read-timeout) left 5 **parent-only** records. One `SAVED` run had 60 symbol, signal, feature, readiness rows. No claim is made that the HTTP exceptions are the only root cause or that an unobserved process did not produce other records. This establishes real publisher-log-to-readback identity evidence, not authenticated PostgreSQL transaction traces.

**Crucial:** original October production collector still can log `FAILED` and return exit code zero; Render provider records all hourly cron jobs ending `successful` through **11:45:06 UTC**, so job-level success is not evidence of durable scan persistence. Unmerged repair branch already includes fail-closed reporting fixes.

## Current PR and acceptance decision

Isolated draft PR #445, earlier inspected head `0a361aaaff3a8706c5915ccec68aaf5f743da5ba` had **11/11 PR workflows SUCCESS**. Retrieved Full Production Test Suite log on exact head: **1,622 passing Python tests plus 101 subtests** in run 45108144380. No submitted independent PR reviews; DBA/security identities and decisions remain absent. This CI validates mocks and disposable synthetic regression scope only.

**Still blocked**: owner-authorised private container access/custody; full `alpha_hunter_private_qa` restoration with exact true production schema/trigger/extension/function/role parity; genuinely durable **30/50/61-symbol concurrency**, statement/client timeouts, lost ACK, retries, rollback, downstream once-only effects, p95/p99 plus WAL/locks; and independently signed DBA and security decisions against immutable final revision, then separate owner-controlled paper-only release.

**Decision:** P0 production defects continue. **PRODUCTION NO-GO.** No assertion of authentic private QA execution in this report.
