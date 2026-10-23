# Canonical monitoring custody repair — draft only

The 23 October read-only audit found a canonical parent claiming 56 children
with zero persisted children and three managed paper positions whose last exit
observations were over the frozen 35-minute monitoring limit. PR #371's child
publication gate alone did not prove durable position observations: a successful
reconciliation return, including the no-quotes early return, could publish.

This change captures the managed-position inventory before reconciliation can
close and remove positions, then reads current-run exit-attempt receipts before
publishing VERIFIED. Every captured position requires exactly one matching
order/decision/symbol/direction receipt, aware observation time within the scan's
35-minute window, a usable outcome, no blockers, and paper-only authority.
Missing/duplicate/mismatched/truncated evidence fails closed. Inventory read
failure does not suppress independent reconciliation. Empty successful inventories
are accepted. Existing historical flags and records are never rewritten.

Local validation: 1,327 passed, two skipped, six subtests passed. The skipped
modules require local PostgreSQL/PostgREST and psycopg; their parent/child fixture
now explicitly supplies an empty managed inventory. This is NOT a claim of new
real-HTTP position-custody integration coverage. Targeted publication/custody/
stage-isolation tests: 30 passed.

## Remaining release gates

- Exercise nonempty inventory and receipt readback through real PostgreSQL 16/17
  and PostgREST, including lost acknowledgement after commit and concurrent exits.
- A newly filled position intentionally skipped by the horizon protocol has no
  fabricated observation: this gate leaves publication pending. Review that
  conservative behavior and define any separate fill/protection proof before a
  successor release; do not silently waive it.
- The managed view excludes historical quarantines and the NMR partial residual.
  This check cannot certify all-ledger protection or repair the residual.
- Receipt existence is not independent quote provenance, real execution, stop
  fillability or historical 35-minute cadence proof. The observation window is
  relative to the source scan, not a guarantee of current wall-clock freshness.
- Inventory and readback are separate reads; no atomic all-position census or
  concurrent-writer lock is introduced. Require deployment/producer isolation.
- Existing VERIFIED parent write precedes final parent acknowledgement readback;
  an ambiguous final response remains a separate release-review concern.
- Obtain independent DBA/security and release review and prove the safe successor
  boundary before merging/deploying. Current R9/R10 identities, deadlines,
  admissions, positions and Primary Hourly stay unchanged.

Production incident remains unresolved by this draft. No database migration,
production deployment, order action, deadline extension or monitoring-limit
increase was performed. The running scanner remains on its existing code.


## 23 October 2026 — independent forward failure observed (READ ONLY)

At 11:43:21.556067 UTC, canonical run
`99c882a155f3bfbdf9dec6cd1ca0fce4` claimed 61 symbols
but retained **zero** corresponding symbol-child rows and **zero**
current-run paper exit-attempt receipts. The immediately preceding
11:23:14.403505 UTC canonical run
`d4c7b7dcb0be0f51957f06c8f2025acf`
had 59/59 persisted children and three exit-attempt receipts.

The new read-only GitHub Actions probe at approximately 11:46 UTC
([run 39948400491](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/39948400491))
saw production `/api/build` HTTP 200 with web commit `8b8037f`,
but `/api/latest` HTTP **503** with the expected fail-closed
`live_data_unavailable` contract. The probe **FAILED intentionally**:
the missing scan evidence is a genuine operational incident, not a
broken assertion to relax. This observation must never be represented
as a successful production repair.

After this independent read, the active canonical producer still
identified commit `33e8820bc8e4e2958e2fc20c7fb80899c4e2e65e`.
The draft successor PR is NOT deployed; live R9/R10 scientific history
and the 35-minute monitoring bound have not been modified.

Additional isolated HTTP tests on this draft branch now exercise a
**nonempty** paper-position inventory and a persisted current-run
receipt over *real local PostgREST and ephemeral PostgreSQL 16/17*:
absence or unusable status must keep the parent PENDING; synthetic
receipt recovery is checked only inside the ephemeral test fixture.
These transport tests intentionally stub the execution/reconciliation
producer and do NOT prove independent quotes, full real PostgREST
transaction semantics, prospective monitoring continuity, or a safe
successor release.

**Release condition is unchanged:** no merge, live migration,
trigger/timeout adjustment, scheduler change, admitted paper order,
manual intervention in existing positions, historical backfill or
test reset. Independent production-incident diagnosis and release
approvals remain open.
