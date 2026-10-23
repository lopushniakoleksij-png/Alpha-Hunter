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
