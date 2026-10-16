# Alpha Hunter P2 — incident → independently read-back journal → alert → recipient evidence

**Review date:** 2026-10-16. **Draft PR #341 ONLY. NO production change, alert, spending, R1 authorization or trading authority.**

## Narrow scope and what actually passed

The **new end-to-end integrity verifier** is deliberately restricted to a single
**synthetic managed paper residual** with source-consistent STOP/TP identifiers
and a **2,101-second** monitoring gap. It does not self-attest general
all-cohort or real operational monitoring. It reuses the existing full source
ledger / raw-quote / signed per-position provenance verifier:
`ops/reviews/successor_p2_source_quote_provenance_contract_v01.py`.

Files:
- `ops/reviews/successor_p2_incident_delivery_lineage_v01.py`: independent
  verifier for signed source, quote, previous/current position receipts, true
  35m breach, signed incident, cross-bound second-journal digest, committed-row
  readback, alert linkage, separately signed mock provider and recipient.
- `tests/test_successor_p2_incident_delivery_lineage_v01.py`: ten adversarial
  offline tests: valid mock chain, incident without breach, source/quote/position
  modification, re-signed wrong order/run/digest, journal omission or forged
  signer, alert/outbox swapping, provider-only acceptance, wrong recipient or
  provider reference, journal outage and missing/replayed evidence.
- `ops/reviews/successor_p2_incident_journal_pg16_v01.py`: on **second
  disposable GitHub Actions PostgreSQL 16 service** only, commit a synthetic
  incident record, establish an independent **new-connection readback** of
  precisely matched incident+bundle digests, reject SQL UPDATE/DELETE through
  an immutable trigger and a conflicting duplicate insert via unique PK,
  and revalidate the incident→outbox→signed mock inbox evidence.
- `.github/workflows/successor-p03-residual-custody-review-v01.yml` runs
  both the ten pure offline tests and the second-DB PostgreSQL behavioral test
  under the existing free CI runner with production credentials set empty.

### Actual CI evidence

On draft commit `7d94865c605f6e1258a70f22866ff34b6d29dc80`:
- [P03 isolated custody workflow 38926753587](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/38926753587):
  **19/19 existing alert negative tests**, **10/10 new lineage tests**,
  **PASS** `P2_EPHEMERAL_SECOND_DB_INCIDENT_OUTBOX_LINKAGE_PASS` proving
  reopen-after-commit, readback, immutability and conflicting-replay rejection
  on a separate disposable localhost PostgreSQL 16 service. The storage and
  keys disappear when CI ends; it is **not independently retained operational
  incident custody**.
- [full Python suite 38926753533](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/38926753533):
  **1,418 Python tests + six subtests PASS**.
- This validates test logic and risk-negative cases, not real source identity,
  independently authenticated venue quote bytes, recipient delivery, actual
  external liveness or 72 real elapsed hours.

## Exact lineage acceptance contract for future reviewer

`SOURCE_REPEATABLE_READ` → `PUBLIC_BITGET_QUOTE_BYTES` →
`PAPER_POSITION_OBSERVATION (prior/current)` →
`ISOLATED_MONITORING_INCIDENT` → **separate journal record hash and
post-commit new-connection readback** → `ENQUEUED` alert signed with immutable
event+incident+journal/source bundle hashes → mock `PROVIDER_ACCEPTED`
bound provider ID → independently signed mock `RECIPIENT_CONFIRMED`
bound same event, recipient, provider ID and exact alert digest.

Every transition compares independently verified digest, event ID, run,
entry-order ID, symbol, source/quote/position observed time and event cause.
Evidence input source and HTTP status are cryptographically **TEST-only**. In
particular, a successful HTTP response, signed mock provider webhook or a
collector-written `delivery_verified=true` is **never** independent recipient
proof. A quote obtained over valid public TLS authenticates the transport
connection, **not** an exchange digital signature on the price.

### Fail-closed outcomes

Any missing/delayed source/quote, altered or swapped incident/order, digests,
unexpected duplicate, unreadable independent journal, partial store, 2,101s
per-position gap, mismatched mock recipient or missing independently witnessed
mock inbox receipt MUST remain `FAIL_CLOSED` / critical diagnostic. No
retrospective source backfill/monitoring PASS. A genuinely unprotected or
quarantined historical residual cannot be made `MANAGED` by this synthetic
test or by its provider/outbox receipt.

## Explicit independent and live blockers

1. **P0 inventory:** historical **NMRUSDT LONG 1.5 paper units** is still
   unprotected/unquarantined; **21** other positive paper residuals quarantined,
   **10** managed with recorded protective IDs; source-complete monitoring
   operational evidence unavailable. Latest previously verified 24h scan
   diagnostic includes 5 parent-only scans: 4 confirmed `57014` SQL errors
   and one 2026-10-16 11:23 UTC ambiguous **15s HTTP POST timeout**.
   Original sealed R10 four integrity failures are **separate** incidents.
2. **R1:** exact hash V3 migration *not* exercised against all twelve source
   relations on disposable PG16+PG17 under production-equivalent rights;
   independent human DBA/security signoff **not received**. Production
   reader/RLS role/schema and auth secrets **not provisioned**.
3. **Independent live source / venue custody:** no authenticated SELECT-only
   live reader, no persistent cross-failure-domain real quote/position
   receipt chain, no approved collector with key management and backup/restore.
4. **Actual alert delivery:** no approved sender domain/provider, sender
   credentials, actual provider receipt, actual recipient inbox proof, or
   independent external deadman. All alert identities are synthetic tokens;
   no real address in GitHub CI.
5. **Operational qualification:** no forward **72 consecutive real hours**
   of independently captured per-position observations; no P3 verified real
   execution-cost evidence; no scientific or live trading release approval.

**Hard authority flags:** production deployment false; R10 admission halted;
trade/order authority false; app/cron main unchanged; R1 separate NO-GO.
Frozen SQL 12s / HTTP 15s / observation maximum 2,100s, no relaxation or
historical repair. **New spend $0**.

## Recommended next approval boundary

Further offline work may generalize this **single-position** end-to-end model
to every positive residual and outage category, with verified independent
incident-to-queued-alert coverage (one deterministic incident ID per cause,
paper-order/run pair, and no vanished quarantines). **Do not represent that
future work as already complete.** Any real observer, persistent independent
journal, sender/recipient test, 72-hour pilot, SQL grant, deployment or
billing requires a separate explicit scoped owner approval and the relevant
security/provider signoffs after R1. Actual independent human DBA signoff
cannot be self-certified by ChatGPT.
