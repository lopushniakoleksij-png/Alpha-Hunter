# P0.3 — Independent quote/alert acceptance, selected trigger parity and release isolation

**Date:** 2 November 2026, UTC. **Decision:** PRODUCTION NO-GO. **Scope:** read-only production checks plus offline isolated GitHub Actions; no external credential tests, migration, merge or deployment.

## Verified work

1. **Actual production role and source-custody metadata** remain captured in `ops/reviews/p03_live_prod_security_baseline_20261102.json` and reproducible SQL `ops/reviews/20261102_p03_supabase_roles_source_READ_ONLY.sql`. The actual `service_role` bypasses RLS, while `anon`/`authenticated` do not. Parent/child tables have RLS enabled, zero policies and broad underlying public grants. These are metadata checks, NOT authenticated public HTTP/Data API authorization tests. Re-run before any approval.
2. **Provider/monitor/alert/recipient chain contract:** `ops/reviews/phase2_p03_quote_alert_custody_contract_v01.py`. It tests SHA-256 of raw quote bytes, the canonical VERIFIED parent and run/position/receipt identity, symbol, independent observer, capture/observation clocks, alert identity, recipient and independent delivery evidence. Missing, swapped, stale or untrusted components reject the claim. It expressly NEVER grants release, orders, or historical first-touch clearance.
3. **17/17 offline unit regressions PASS**, dedicated independent quote/alert workflow [41455803474](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/41455803474), with zero production credentials. Even the test fixture containing *synthetically asserted* independent witness and recipient confirmation cannot provide proof that those services actually attested anything. This is contract validity, not field-proven custody.
4. **Selected trigger-source parity:** Fresh production read-only `pg_get_functiondef` hash comparison with archived isolated fixtures found **11/11 core+account/protective routines' recorded md5 equal to live definitions**, plus **3/3 sealed R8/R9/R10 activation guard bodies byte-identical to live SQL after accounting for a fixture's terminating SQL semicolon**. This checks 14 selected critical functions, NOT all dependency edges or actual live gateway behavior.
5. GitHub PR #378 is DRAFT and unmerged. Its independent review submissions list is **empty**. Connected Supabase development branches list is empty. No reviewer approval can be inferred from the GitHub Actions successes.

## P0.3 blockers and exact acceptance evidence still required

| Gate | Current evidence | Required next verified result |
|---|---|---|
| Production Supabase role boundary | RLS/grants catalog; synthetic JWT PostgREST PG16/17 | Independently managed *actual* API credentials, actor-based GET/denied writes via real project API, service_role least-privilege and RPC route inspection, without exposing key material |
| Provider quote identity | Independent public TLS ticker/orderbook transport capture; raw hashes | Independently authenticated provider-origin and durable external custody tied to actual run/receipt/symbol/timestamps; prospective only |
| Notification delivery | Offline strict identity/recipient ACK validator | Real delivery provider's durable message ID and recipient-confirmed acknowledgement, independently verifiable, not just app assertion |
| Scientific protection exceptions | Three first-entry same-snapshot ambiguous positions | Contemporaneous independent first stop/target ordering; *never infer* it from later quotes or backfill historical outcomes |
| Trigger/DBA parity | 14 critical definitions checked; main subset full-width stress PG16/17 | Complete actual dependency graph, real cost-floor fee lineage, actual service-role execution path, independent DBA isolation, rollback and explicit signed review |
| GitHub deployment controls | `main` unprotected; protected Render cron `main`, `autoDeploy=yes` | Owner-approved enforceable ruleset and separate non-`main`, manual-deploy isolated successor. Any deployment must pin immutable reviewed SHA and demonstrate zero scanner impact |
| Approval | No PR #378 review submissions | Independent DBA, security, science/risk, ops and owner signoffs on exact tested source before *separate* production authorization |

**Operational safety:** protected hourly cron on original schedule; R9/R10, frozen historical outcomes, paper positions and live-order restrictions unchanged. No production migration, schema/grant change, branch protection modification, main merge, deployment, credential exposure, live order, or new purchased infrastructure. **£0 new spending.**

**Do not treat a synthetic witness Boolean, GitHub green CI, or documentation sign-off placeholder as independent real-world provider authentication or release permission.**
