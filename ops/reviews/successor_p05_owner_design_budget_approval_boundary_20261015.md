# P0.5 owner-approved design direction and CONDITIONAL budget plan — 2026-10-15

**Approval interpretation (updated 2026-10-15):** The owner approved the successor-monitoring architecture and expressly accepted the proposed **USD 25 per calendar month maximum budget ceiling** for planning, including storage and usage. The owner also explicitly instructed **DO NOT PAY YET**. This is a confirmed financial *limit*, **NOT consent to any payment, paid subscription, resource creation, billing activation, deployment, or production credential/database change**. Any actual spending and deployment still require a separate explicit owner authorisation after vendor/role/security review; spending exceeding the cap is not allowed without further explicit approval.

## Revenue-first funding hold — owner instruction, 2026-10-15

**Binding commercial priority: EARN FIRST, INVEST LATER.** The owner explicitly instructed that we must generate actual earned money before spending on Alpha Hunter infrastructure. Accordingly, **all new cash expenditure, paid services, billable trials, metered infrastructure, paid database/storage/notification plans and payment authorisations are ON HOLD until verifiable earned revenue exists, even if a USD 25/month ceiling was already approved for planning.** A budget ceiling is NOT a spending mandate or payment approval.

**Release of the hold requires BOTH:** (1) demonstrated actual received funds from legitimate earned activity (not hypothetical funding, paper PnL, projected earnings, backtests or unsettled trade profits); AND (2) a fresh, explicit owner approval of the exact charge/provider and recurrent spending. The USD 25/month planning ceiling remains an upper limit if a future payment is separately approved; it is not an instruction to begin billing automatically. Never initiate trials that convert to paid subscriptions, attach a payment method, create a paid instance or make changes that incur charges while this hold is in force.

**Permitted during the hold:** read-only audits, planning and synthetic/CI testing within already available no-additional-cost limits, maintaining unchanged Primary Hourly, paper position management and frozen R10 protections, and revenue-generation efforts outside the paper system. Even free experiments must not introduce production side effects, historical backfills, duplicate scans, excessive quota usage or any trading permissions. If a seemingly free step may create later charges, stop and request explicit owner review.

**Paper trading is scientific evidence only and cannot be treated as spendable income.** The next funded service design remains a future option, not today's priority. Current financial authorisation: **USD 0 new spending**.

## Protected production boundary

- Preserve Alpha Hunter Primary Hourly task enabled, hourly, non-expiring.
- Render canonical `main` cron `crn-d9nmbjbm8hqs73elu6hg`, autoDeploy=yes, scheduled `0 * * * *`; leave unchanged.
- Preserve original R10 scientific identity/fingerprint, 24h horizon, 35-minute monitoring limit, original observations/failures, admission halt, 37 admitted orders, and 10 currently managed paper positions; never restart, recompute a winning test or fabricate exits.
- All historic paper positive residuals remain in the ledger, including 21 quarantined and 1 unprotected/unexplained NMRUSDT LONG 1.5 modeled units at the 2026-10-15 read-only baseline. Quarantine is not a successful close or evidence of protection.
- No order entry, trade modification, exchange credentials, Supabase write/DDL permissions, merge to main, production scheduler change, or service creation is authorised by this document.

## Proposed pilot architecture and price book

Official price pages checked 2026-10-15:

| Proposed component | Published starting monthly price | Usage/safety assumption |
|---|---:|---|
| Dedicated isolated Render continuous background worker, 0.5c-512mb | USD 7 | No internet-facing HTTP routes, no scanner imports, autoDeploy off |
| Dedicated **paid** Render Postgres custody, 0.1c-256mb | USD 6 | Includes 1GB storage and paid-instance PITR subject to workspace recovery window. Not free expiring DB. Insufficient for cross-provider outage survival by itself |
| Offsite Cloudflare R2 Standard backups | USD 0 **only within free allowance** | 10 GB-month and included standard operations; bucket/account not created; encryption, retention, integrity checks and restore testing required |
| Resend transactional failure-email channel | USD 0 **only within free allowance** | 3,000 emails/month and 100/day; separate verified sender domain and receiver; real delivery must be checked, no auto-claims |
| Healthchecks.io independent dead-man monitor | USD 0 **only within free allowance** | 20 job checks, logs capped to 100 per job; independent alert test required, not durable scientific custody |
| **Nominal recurring baseline** | **USD 13/month** | Excludes taxes, above-free usage, optional paid alerts, backup/key services, storage and bandwidth overruns |
| **Approved financial planning ceiling — not spending permission** | **USD 25/month MAXIMUM** | Approved by owner 2026-10-15 for planning only. No payment, subscription, billed resource, upgrades or overruns are authorised. USD 12 nominal headroom against the USD 13 baseline |

Sources: https://render.com/pricing ; https://render.com/docs/postgresql-backups ; https://developers.cloudflare.com/r2/pricing/ ; https://resend.com/pricing ; https://healthchecks.io/pricing/ .

The USD 25 cap is a small *72-hour prospective pilot* proposal, not a claim of high-availability production-grade service. Explicitly reject a proposed build if a resilient alert provider, retention or traffic needs exceed the cap; re-cost and request fresh approval. Free-tier availability is not an SLA. Two services on Render may share a provider-failure domain; offsite R2 and independent heartbeat reduce but do not eliminate correlated failures. A DB at the cheapest size is a performance hypothesis, not production sizing approval.

## Least-privilege credentials gate (not yet authorised to create)

- Independent dedicated PostgreSQL LOGIN source reader, with minimal SELECT grants to the exact public paper-order/entry-fill/exit-fill/protection/quarantine and immutable scientific-identity sources. RLS review must ensure no BYPASSRLS or superuser role inheritance. No access to production service-role environment or shared Render secret group.
- Test a REAL consistent single transaction `REPEATABLE READ READ ONLY` on the chosen Supabase connection path, source table count, row IDs, snapshot/watermark, captured time, manifest verification and bounded query cost. READ ONLY session flag alone is NOT sufficient; database grants must enforce inability to write.
- Ensure direct/pooler compatibility, TLS, short timeout, connection limit and backoff, external allowlist if available, and hash-of-source transaction evidence captured independently. Empty/missing ledger and stale current-view positions must FAIL CLOSED.
- Separate insertion-only custody credential, readonly verification credential and alert dispatcher credential; encrypted persistent signing-key custody with rotation and emergency revocation. Never embed key/password in repository or CI logs.
- Restore test separately from primary data store and verify receipts from genuine forward captures, not historical "reconstructed" records.

## Notification and evidence integrity gate

- All >35-minute gaps, missing sealed inventory, source or quote failure, journal failure, collector liveness loss, unprotected residuals and changed quarantines create append-only idempotent outbox events.
- Distinguish created/queued, provider accepted, recipient delivered and human acknowledged. Only a controlled real-world delivery test can establish a VERIFIED alert delivery; simulated GitHub Actions events do not qualify.
- External dead-man check is independent of both worker and receipt database. If all paths die simultaneously, classify UNKNOWN and use outside-provider liveness alert rather than asserting safety.

## Prospective 35-minute proof before considering promotion

A separate *owner-approved* persistent shadow service would attempt source + position observations approximately every 5 minutes (a proposed engineering target, **not** a modification to frozen R10). A REVIEW-PROPOSED 72-hour forward window must establish *all* managed position receipts and no gap above exactly 2,100 seconds using directly authenticated live source transactions and separately sealed market-data provenance, under primary-timeout, venue-timeout, journal-outage, collector-death, replay and recovery injections. First receipt cannot retrospectively certify preactivation monitoring. All-cohort residual ledger and incidents remain visible, including NMR. No failed existing cohort can be "healed" or promoted from this pilot. Scientific pass, R10 paper admissions and live trading remain blocked.

## Separate owner authorisations needed before any implementation

1. **COMPLETED — budget ceiling only:** Owner approved **USD 25/month maximum** on 2026-10-15 and explicitly withheld payment permission. All actual paid subscriptions, billing activation and charges remain subject to separate approval. If total fees, taxes, storage and usage cannot be held within USD 25, reject the proposal and request a revised ceiling; never exceed the approved cap.
2. Confirm exact intended paid worker / paid database supplier and that user accepts recurring billing, plus R2 backup account, email sender/recipient, and external heartbeat delivery channel; review their access/privacy requirements.
3. Approve the precise least-privilege source grants, secure secret-creation workflow and credential administrator, after source security review. Any database `CREATE ROLE`/GRANT is a production configuration change and needs its own explicit approval.
4. Approve a pinned successor build SHA, off-main isolated Render service creation, independently managed custody account, forward start and bounded pilot period; no default merge or auto-deploy.
5. Preserve original R10/Primary Hourly and separately check both after any later approved release and rollback; do not modify paper positions.

**Current decision (2026-10-15): DESIGN DIRECTION APPROVED; USD 25/MONTH BUDGET CEILING APPROVED FOR PLANNING ONLY; PAYMENT/BILLING NOT AUTHORISED; PAID RESOURCE CREATION, SOURCE ROLE/GRANT, AND DEPLOYMENT NO-GO UNTIL A SEPARATE EXPLICIT OWNER APPROVAL.**
