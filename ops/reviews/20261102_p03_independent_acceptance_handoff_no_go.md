# Alpha Hunter — P0.3 Independent Acceptance Handoff (NO-GO)
**Prepared 2026-11-02 UTC. Research draft only. No independent sign-off is inferred.**

## Immutable, read-only baseline
- Pull request **#378** head `782dc4843b857353c120f6ac0aa2dc82346894af`: draft, unmerged; **zero independent submitted reviews**.
- GitHub `main` at `b71c87d0b5963a5ca10c23d82b67a0edd47f120c`: **branch protection false**.
- Render P0 protected cron `crn-d9nmbjbm8hqs73elu6hg`: `main`, `autoDeploy=yes`, `0 * * * *`, unsuspended. Do NOT merge, edit or redeploy.
- Production Supabase 3 managed paper positions, each with two recorded protective legs; all 3 have `unresolved_protective_evidence=true`. Do not infer historical stop/target order from later quotes.
- Previous bounded isolated database, synthetic HTTP role and quote/alert contract CI results **are not independent real-world acceptance**.

## Independent gate acceptance — all required, none self-signable

| Approval owner | Required evidence | Current decision |
|---|---|---|
| Independent DBA | Catalog function/index/trigger graph plus exact live cost-floor execution path; isolated PG16/17 signed source SHA, full-width PostgREST WAL/p99, failure replay and proven migration + rollback plan | **NOT APPROVED** |
| Independent security reviewer | Real project API via independently managed `anon`/`authenticated` tokens; `service_role` read-only verification from separately secured reviewer context; cross-check RLS/SECURITY DEFINER/Data API; no service secret copied into GitHub, logs, files or this conversation | **NOT APPROVED** |
| Independent quote custodian | Prospective provider-origin validation, raw quote hash/source/timestamps in independent immutable evidence, exact run/symbol/position linkage; do not promote legacy historical quote ordering | **NOT APPROVED** |
| Delivery/operations reviewer | Real alert provider message ID and recipient-confirmed delivery evidence, matching an immutable alert/monitor record; prove actual success, retry and failed delivery | **NOT APPROVED** |
| Independent scientific/risk reviewer | Evidence lineage and censoring policy for historical first-entry ambiguity, protected R8/R9/R10 freeze and paper-only 35-minute monitoring requirement | **NOT APPROVED** |
| Release owner | Repository enforceable protected-main rules, distinct successor **non-main** Git/Render service with `autoDeploy=no`, no shared protected cron, pin immutable SHA, paper-only canary, zero-interference/rollback evidence | **NOT APPROVED** |
| Owner release authorisation | Written approval **after** above signatures and exact unchanged source SHA; separately approve any money/infrastructure | **NOT AUTHORISED** |

## Approved scope of continued work (no production changes)
1. Ask each independent reviewer to record identity, exact immutable commit, evidence artifact digests, inspection timestamp, reproducible validation, decision and counter-signature *in a reviewer-controlled system*.
2. Test actual API permissions first with **read-only operations**. Any negative write test against a live database is **forbidden**. Write-denial tests only in an explicitly approved disposable/isolated Supabase environment using independently managed credentials and no real positions.
3. All future external quote/alert evidence must be collected prospectively and tied to exact source/run/position/time. No late quote can reconstruct an earlier executable stop/target sequence.
4. Identify and obtain approval for GitHub protection and a distinct, pre-existing/zero-cost successor service, or remain NO-GO without provisioning.
5. Keep all real-world review secrets outside chat, GitHub CI and research logs. No existing system credentials may be copied into a test artifact.

## Mandatory abort conditions
- Any live R9/R10 reset, historical rewrite, paper-position modification, live order permission, unverifiable proof, unexpectedly modified `main`/cron, unapproved service charge, lost monitoring evidence, unbounded privilege or unresolved alert acknowledgement.
- A reviewer cannot independently reproduce the result or rollback would mutate the protected scanner.

**Decision:** `PRODUCTION_NO_GO`. Independent signatures: **0 supplied**. Safe successor deployment: **NOT APPROVED**. Actual role-API / provider-attested / alert-recipient custody: **NOT VERIFIED**. No merge, deployment, database migration, order, cost or protected workflow change authorised.
