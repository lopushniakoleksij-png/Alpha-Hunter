# P2 operational position/quote evidence + alert delivery — release gate

**23 October 2026 | DRAFT PR #341 | zero additional infrastructure or payment | no production change**

## What was actually established

A genuine, public-only, unauthenticated (no API key) Bitget USDT-M ticker
HTTPS capture now has an inspectable, **time-limited GitHub Actions artifact**
outside the Alpha Hunter source database:

- [Verified GitHub Actions run 39960541280](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/39960541280):
  - Original P02 transport acceptance: two real BTCUSDT HTTPS ticker
    samples; TLS CA/hostname verified; two signed receipts committed and
    independently read back from an **ephemeral, second local PostgreSQL 16
    service**; injected primary DB timeout, secondary DB timeout and socket
    timeout tested; **PASS**. The ephemeral journal was deleted with the runner.
  - One-shot extra public-only quotes for **NIGHTUSDT** and **SOONUSDT**
    (symbols independently identified earlier from the modeled paper
    managed view), two of two captures **PASS**. These captures are independent
    public quotes *about market symbols*, NOT independently authenticated
    position snapshots, historical R10 receipts or active exit observations.
  - [Artifact 12503334885](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/39960541280/artifacts/12503334885)
    includes the original returned public ticker JSON response bytes, the
    read-back-checked SHA-256 hashes, timestamp, specific public symbol,
    one-shot request ID, and explicit no-authority provenance fields.
    **Expires 22 November 2026, 13:22 UTC** (30-day bounded retention).
    Its GitHub content is inspectable but NOT legally/audit-grade permanent
    append-only custody; workflow owners can delete artifacts.
- Exact branch content commit for this proof:
  `f75752fc0f1a84bca84b1f14334ba920bed3d4ab`.
- The isolated full suite, P02 and P03 receipt/alert negative tests on this
  revision passed. No user or provider notification was dispatched.

## Necessary live position evidence still absent

The currently connected Supabase read-only catalog check at
2026-10-23 13:17:38 UTC found all **12 required physical source tables**
present, all **12 RLS-enabled**, **zero** deployed R1 observer policies,
**zero** dedicated P2 reader/projection roles, and **zero** P2 redacted
reader schema. An administrative read-only SQL result collected from the
existing account **is not** an independent least-privileged as-of-run
capture. Do not represent a `quote_source` string or price match as an
independent authenticated source receipt.

Independent acceptance still requires an owner/DBA-approved reader with
NOINHERIT/NOBYPASSRLS and explicit column-level SELECT scopes across all
12 source relations, role-specific RLS, privacy-reviewed redacted views,
verified TLS, a consistent `REPEATABLE READ READ ONLY` source snapshot
and full all-cohort fill/exit residual reconciliation including NMR.
The previously prepared R1 forward/rollback V3 proposals have **not**
been approved or applied in production.

## Live alert delivery and long-term custody still absent

The GitHub artifacts above are proof of **two independent venue-market
symbol captures and a disposable receipt-journal exercise**, not proof of
durable incident **delivery**. There is no approved independent persistent
journal, production custody service, externally independent dead-man,
verified domain/sender, authorized live test or recipient inbox receipt.
The mock CI event lineage remains a synthetic success only. No mail to a
private address, provider configuration, or production role was attempted.

Three independently approved prerequisites are mandatory before a real
end-to-end pilot:

1. **R1 — source access:** exact 12-table V3 role/RLS/field redaction
   rehearsal on PG16/17 using the unmodified final SQL, independent
   DBA/security sign-off, documented change/rollback, *separate owner
   consent to apply the role*. No source scientific/cron table mutation.
2. **R2 — observer and independent evidence custody:** separately
   controlled persistent journal and secure source collector, real
   immutable long-lived signing keys, retention and restore testing,
   separate watchdog for simultaneous source/journal/collector outage.
   Any paid provider requires advance explicit itemized spending consent;
   current spending approval is **$0**.
3. **R3 — end-to-end delivery:** approved dedicated sender/provider and
   private destination, real controlled test approval, journal commit
   read-back, provider-accepted message ID, separately verified recipient
   inbox receipt, deduplication and recorded delivery failure/escalation.

Only then can a **new successor-only prospective 72-hour operational
qualification** be proposed. The frozen existing R10 30-day / 100-trade
scientific requirements, original integrity failures and **35-minute =
2,100-second** maximum remain unchanged. Neither historical signal
profitability nor trading authority is established by this quote proof.

**DECISION:** P02 public venue capture proof = PASS (narrow, time-limited).
Independent all-residual source position custody = BLOCKED.
Long-lived independent journal and real alert delivery = BLOCKED.
Production or scientific promotion = NO-GO.
No merge, deployment, production credential/role/policy changes, alert
messages, order admission, live trades, cron interruption, test reset or spend.
