# P2 P0.7 — offline source-security and real-delivery release contract
**16 October 2026 | reviewed draft PR #341 only | NOT deployment permission**

## Decision scope
This review closes the *offline model/test-specification* tasks only after the
exact branch-head isolated CI completes green. Even a complete offline PASS
**must not** be reported as independently authenticated live position receipts,
actual email delivery, an operational external sentinel, or a validated 72-hour
forward pilot. None of the following was created or authorized: Supabase role,
RLS policy, privileges, provisioned sender, real email, persistent receipt DB,
background observer, subscription, promotion, real exchange order.

Owner-designated Alpha Hunter alert recipient exists privately. Its plaintext
address stays out of repository, PR comments, test events, CI, sample messages,
logs and artifacts. A future approved sender must take it from a dedicated
secret `AH_P2_ALERT_TO` (restricted destination config, not an app-wide shared
env group); do not send an email simply because it has been designated.
A verified sender domain and independently consented **real** delivery test
remain mandatory before any operational alert-delivery PASS.

## A. Production source security: checked current database metadata, no writes
- Named source set: **12 physical** `public.alpha_hunter_*` paper/canonical tables
  (orders, entry fills, exit fills, exit attempts, protective orders, paper events,
  exit activation, 3 quarantines, parent and child snapshots). Security-invoker
  protection view adds a read dependency on 7 of those physical tables. This
  view is a managed-only convenience and **cannot** replace an independently
  complete *all-cohort* entry-minus-exit residual manifest. Historical NMR-like
  partially filled orders excluded from the view remain fail-visible.
- Observed all underlying scoped physical relations had RLS enabled but zero
  policies for a new ordinary observer. Default-deny with no policy must produce
  `SOURCE_ACCESS_UNKNOWN`, never `ZERO_POSITIONS`. `postgres` and
  `service_role` bypass RLS; neither is an acceptable observer identity.
- Isolated PG16 scope regression exercises **all 12 named relation identities on
  representative synthetic column subsets**, RLS policy drop/revoke, security
  invoker view, 1.5-unit historical partial residual, anomalous `paper_only=false`
  source flag, and denied restricted data/INSERT/UPDATE/DELETE/CREATE ROLE/SET ROLE.
  Separate 3-table role test checks `REPEATABLE READ READ ONLY`. This proves
  the *modeled policy design* in disposable PostgreSQL, not actual production
  security boundaries, exact full live data privileges or pooler behavior.

### Locked live change-request prerequisites (NO migration now)
1. Review **per-column** SELECT necessity, especially JSON `evidence` and
   `payload`, at all 12 base relations and the security-invoker view. Final
   grants must be allowlisted, explicit, never `SELECT *` or global defaults.
   Excluding a source row via policy `paper_only=true` is impermissible because
   it would hide anomalous entries. Apply role-specific FOR SELECT policies.
2. New dedicated LOGIN with NOINHERIT, NOBYPASSRLS, NOCREATEDB, NOCREATEROLE,
   NOSUPERUSER, no privileged memberships, no writable routine EXECUTE,
   no schema CREATE, no public/shared key path; distinct read-only DB credentials
   with separate storage, planned rotation/revocation. Catalog negative tests
   must check direct AND inherited effective privileges.
3. Confirm TLS and direct/session pooler behavior with an **actual** authenticated
   read-only transaction, source identity and server clock, `REPEATABLE READ`
   snapshot across all cohorts with bounded row count and timeout. Record
   independent commit/read proof, not just a caller-written `complete=true`.
   Every partial, missing, empty-from-denial or stale read => `INVENTORY_UNKNOWN`.
4. Benchmark worst-case query cost/index/scanner contention with a **read-only**
   approved capture before allowing 5-minute collection. It must not compete
   with Primary Hourly, change the frozen 35m horizon or enable admissions.
5. Migration review must provide exact SQL/role diff, test-only rehearsal,
   approval, change window, independent verification, role revocation rollback;
   no write to source scientific R10 rows, no scanner deployment and no backfill.

## B. Independent delivery: offline proof states and fraud-resistant contract
Existing P03 isolated journal persists immutable *NOT_DISPATCHED* diagnostic
outbox records on a disposable second PG16 host; its PASS is **not** provider
delivery, recipient confirmation or retention after a CI runner exits.

The added pure Python no-network acceptance model tests:
- `ENQUEUED` in local custody is never `SENT` or `DELIVERED`.
- Provider **accepted** with bound message ID is only `PROVIDER_ACCEPTED`.
- A provider self-report such as delivered/opened, including a properly signed
  provider webhook, is NOT independent actual inbox proof.
- Independent **recipient-confirmation** proof must bind exact immutable alert
  digest, synthetic destination token, provider message ID and verified
  independent recipient signer; human acknowledgement is a separate step.
- Every source event/receipt is append-linked to predecessor digest and
  authenticated by role-separated TEST HMAC signers. Wrong recipient, event,
  chain, signature, reordered clock, out-of-order sequence, spoofed provider
  acting as recipient, replay/concurrent conflict and missing/outage stage fail.
- A journal/dispatcher outage or lost independent sentinel must raise a
  fail-visible diagnostic. Exactly 2,100s is permitted; 2,101s is a breach.
- Every possible test result explicitly reports
  `actual_alert_delivery_verified=false`,
  `real_provider_acceptance_verified=false`, and
  `independent_long_term_durability_verified=false`.
  HMACs and receipts here are **synthetic**, never real network/provider proofs.

### Real-world delivery acceptance later (NOT attempted, no sender key)
1. Owner must approve a dedicated sender domain, deliverability/privacy terms
   and provider, recipients and channel, exact bounded email subjects/severity,
   no paper PII/account secrets, escalation/de-dupe and incident retention.
   Resend is a proposal, **not** an installed sender. Do not leak recipient email
   in PR/CI, a third party unauthorised mail service or logs.
2. A future event must be written first to independently persistent append-only
   receipt custody (read-back after commit, backups/restoration verified) with
   an immutable outbox message ID and payload hash. For one alarm, retain
   `QUEUED` / `PROVIDER_ACCEPTED` / provider report / confirmed recipient inbox
   arrival / human acknowledgement as independently verified distinct receipts.
   No successful status on 2xx, missing webhook, expired token, or failed send.
3. Provider callback authenticity (signature with rotation, timestamp, expected
   sender and message ID, duplicate/replay protection) is necessary but
   insufficient to prove inbox receipt. Delivery test must verify recipient
   possession via separately authenticated signed/acknowledged receipt path.
4. Independent dead-man watcher must detect collector+journal failure outside
   their shared provider failure domain; mock heartbeat != real alarm.
   Separate receipts and explicit owner acceptance required for forced source
   timeout 57014, venue outage, journal failure, worker death and dispatcher
   delivery outage. Failures and >35m gaps remain historical incidents, never
   retrospective PASS after recovery.
5. Outbound email limits/quotas and incident storm deduping must be budgeted.
   Reject a path without provider-accepted message, separately received
   destination evidence and explicitly tracked undelivered/error states.

## C. Finance, cohorts and hard safe boundary
- Existing maximum monthly **USD 25 is a planning CEILING**, not spend
  authorization. The binding **earn-first / USD 0 new spending** instruction
  prohibits billable resources or trials converting to paid. New vendor, role,
  notification provider, worker, DB or key cannot be created here.
- New P2 prospective observer may be planned off-main with a ~5-minute
  *engineering cadence*, but no actual collector or independent journal is
  approved or running. Frozen original R10 **35 minutes = 2,100 seconds**
  remains unchanged; any 2,101s gap fails. R10 admissions halted, four
  original integrity failures immutable, original cutoff/fingerprint intact,
  original paper positions managed by unchanged Primary Hourly.
- Subsequent **72 actual consecutive hours** of authenticated forward source/
  market quotes/managed-position receipts and independently delivered critical
  failure alarms are REQUIRED before a controlled successor pilot verdict.
  Synthetic 72h simulations or green CI cannot start/complete that period.
- P3 cost-model profitability and any new orders remain separately blocked.

## Expected scoped review verdict
**OFFLINE RLS MODEL: PASS conditional on exact-head CI.**
**OFFLINE DELIVERY NEGATIVE MODEL: PASS conditional on exact-head CI.**
**LIVE SOURCE ACCESS: BLOCKED. REAL ALERT DELIVERY: BLOCKED.
DURABLE CROSS-FAILURE-DOMAIN CUSTODY: BLOCKED. 72H PILOT: NOT STARTED.
SPEND: $0. MERGE/DEPLOY: PROHIBITED.**
