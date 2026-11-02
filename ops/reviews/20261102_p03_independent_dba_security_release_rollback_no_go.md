# Alpha Hunter P0.3 — Independent DBA/security acceptance and collision-proof release plan

**Date:** 2026-11-02 UTC  
**Disposition:** **PRODUCTION NO-GO**, no independent reviewer approved release.  
**Current draft:** PR #378 is stacked on unmerged #371, NOT main.  
**Operational constraint:** £0 incremental spending, no trading authority, no restart of frozen R8/R9/R10 test, no intervention on protected P0 Primary Hourly.

## Evidence collected DIRECTLY from production via SELECT-only access

### Actual role metadata and permission boundary

- PostgreSQL version 17.6.
- `anon` and `authenticated`: `rolbypassrls=false`, not login-enabled. `authenticator` login-enabled, without bypass. `service_role`: `rolbypassrls=true` (also not directly login-enabled); PostgreSQL owner `postgres` has RLS bypass.
- Parent and symbol snapshot tables have RLS **ON** with **zero policies**. Both public API roles nonetheless hold underlying SELECT/INSERT/UPDATE/DELETE SQL grants. Under ordinary role enforcement, RLS with no policies denies row access, but the underlying grants should still be reviewed for least privilege; do not call a SQL GRANT alone an actual exposed row.
- Paper-exit receipts, execution decision freezes, account-state and open-position snapshots have RLS ON, zero policies, anon/auth SELECT/INSERT absent, service_role INSERT allowed. Profitability activations have RLS ON, zero policies, no service_role INSERT grant (append-only scientific activation).
- The cost-floor and open-paper-protection views have `security_invoker=true` and `security_barrier=true`, and public roles lack SELECT grant.
- Five Alpha Hunter `SECURITY DEFINER` functions exist in public; zero are executable by anon/auth. Zero anonymous-executable private security definers; private schema lacks anon/auth USAGE. 26 (at time of inspection) private security-definer routines are service_role executable, with observed `search_path=""`. A read-only text scan found no dynamic SQL `EXECUTE` among this selected set; independent code/security penetration review remains REQUIRED.
- A single public non-definer trigger utility had anon/auth SQL EXECUTE privilege and warrants review, but metadata alone does NOT establish it can be used as a public RPC.
- **Missing verification:** real Supabase API gateway JWT role switching, service_role credential custody and scopes, callable RPC routes, token replay and actual end-to-end external HTTP response. Never copy or expose the service_role token to GitHub Actions or public reviewers.

### Source provenance and alert custody

Read-only data as of this review: 168 paper exit monitoring receipts since November 1; all 168 refer to existing parent scans, **0** refer to parent publication state `VERIFIED`; all 168 flagged `captured_quote_only=true`; **65** lack a quote-source label; **0** include a `provider_signature` field. This does not refute public exchange TLS transport capture in separate prospective CI; it DOES prevent calling historical market observations independently provider-attested.

A metadata search returned no dedicated Alpha Hunter alert/notify/acknowledgement/delivery relations matching those names. This is **not proof no external provider notification exists**, only that durable independent recipient acknowledgement was not verified by this database search.

The 3 existing paper positions remain `ENTRY_AND_EXIT_ORDERING_AMBIGUOUS_SAME_SNAPSHOT` with two recorded modeled protective legs each; they have NOT been independently resolved or reclassified.

### Deployment collision risk (read-only GitHub/Render evidence)

- Render protected cron `crn-d9nmbjbm8hqs73elu6hg`: branch `main`, `autoDeploy=yes`, schedule `0 * * * *`, not suspended.
- Existing live web service `srv-d9notmtaeets73cdrbc0`: branch `main`, `autoDeploy=no`.
- GitHub API reports repository branch `main` currently `protected=false`; do NOT rely on draft PR convention as technical merge prevention.
- Any merge into `main` may auto-deploy the protected scanner. Even a web-only code change must be presumed risky until independently demonstrated otherwise.

## P0.3 execution: no permission escalation

Frozen metadata snapshot: `ops/reviews/p03_live_prod_security_baseline_20261102.json`. Read-only reviewer queries: `ops/reviews/20261102_p03_supabase_roles_source_READ_ONLY.sql`. Offline classifier: `ops/reviews/phase2_p03_security_release_gate_v01.py` and unit regressions. The classifier ALWAYS returns `PRODUCTION_NO_GO`; it cannot issue a production credential, invoke a server action, merge a branch or deploy. Re-run read-only evidence before a reviewer acts: this snapshot is not proof against future drift.

### Required independent acceptance, ALL must be documented and checked

1. **DBA**: independently reproduce exact SQL migration/index candidate and rollback on isolated PostgreSQL 16/17 under RLS and production-like partition/index/full-size conditions; reconcile trigger graph including payoff/real cost evidence, R8/R9/R10 activating dependencies, observation cancellation + historical evidence custody. Record signed SQL hashes, failed-injection outcomes, WAL, locks, p99 and rollback. Production SQL remains forbidden before approval.
2. **Security**: authorised end-to-end tests of the *real service_role / anon / authenticated* Supabase gateway with independently managed credentials; verify proxy role identity, schema USAGE, direct table grants, RLS, invoker views, public RPC/SECURITY DEFINER, token/secret custody, and proof no client can insert protected scanner or order evidence. If key exposure is discovered, separately approve rotation; do not paste keys into review artifacts.
3. **Provenance/science**: independently capture exchange quote source + provider timestamps + exact raw bytes, provider identity/proof strength, immutable storage and confirmed recipient alert delivery. Each prior/current receipt must link to independently observed source-run and position identity. Never backfill previously ambiguous stop/target ordering. No R10 admission/profitability promotion.
4. **Operations**: independent service graph: identify exact protected scanner ID, intended successor target ID, repository source branch and autosettings, service secrets/DB separation, and a **reviewed immutable SHA**. Confirm no other automation or Render cron can deploy from the candidate branch. Prove canary and rollback while the protected cron continues unchanged.
5. **Owner authorization**: separate explicit written approval for any production change. No paid infrastructure without explicit spend approval.

### Controlled successor-only release method (PLAN, NOT executed)

- **Do not merge to `main`.** Before any release, enable/enforce GitHub repository rulesets/branch protection requiring independent review, checks and disallowing unapproved direct pushes and bypass. That setting change itself needs owner approval; it has NOT happened.
- Use an **approved, separately isolated successor service** tracking a dedicated non-`main` release branch and `autoDeploy=no`. It must be demonstrated incapable of targeting the protected Render cron, web service or original R9/R10 dataset. Never use current production web service as a surrogate for isolation without authorisation.
- Pin the exact reviewed commit SHA, not a floating `main`, and preserve all GHA evidence digests; deploy to the approved successor only after DBA/security/science/ops written signatures.
- Start a **read-only, paper-only canary**, with `trade_permission=false`, `order_path=NONE`, admissions halted, no real-order/exchange credentials, and no independent user-facing profit claims. Confirm canonical child/source/monitoring/alert custody and <=35-minute protection observations.
- **Rollback of successor only:** stop its traffic/cron, switch only its approved target back to previously pinned SHA, verify no shared production DB writes or orphan alert records. If no safe isolated rollback exists, ABORT without attempting deployment.
- Any production database DDL/index migration is a **separate** named DBA-approved change with rehearsed backup, before/after diffs, transaction or reverse-migration proof, and explicit rollback contingency. There is no permission to run it here.
- On any mismatched source/quote/position, RLS authorization anomaly, missing child snapshot, stale monitoring, duplicated writes, lost recipient acknowledgement, increased database latency or cost, fail closed, preserve evidence, and block release.

### Reviewer signoff — deliberately blank

| Required authority | Name | Exact source/CI evidence reviewed | Decision | Date |
|---|---|---|---|---|
| Independent DBA | Unassigned | Not signed | NOT APPROVED | — |
| Independent security reviewer | Unassigned | Not signed | NOT APPROVED | — |
| Independent scientific / risk reviewer | Unassigned | Not signed | NOT APPROVED | — |
| Operations release owner | Unassigned | Not signed | NOT APPROVED | — |
| Final owner production release authorization | Unassigned | Not signed | NOT APPROVED | — |

**Decision: all previous bounded isolated checks can remain PASS, but production-equivalent security, full external source custody and safe auto-deploy separation are NOT approved. Production remains NO-GO. No migration, scanner edit, R9/R10 or paper-position action, main merge, real trading, new infrastructure or spend.**
