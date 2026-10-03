# Participation v0.2 database contract tests

Run `npm ci --ignore-scripts && npm test` in this directory (Node 22+).
The pinned PGlite dependency executes PostgreSQL in an empty local WASM database.
No production connection, credential or market data is used.

The actual migration is executed, using minimal synthetic upstream tables and
inert cron function stubs. A historical spec registration is seeded before the
migration so horizon boundaries can be tested without waiting 24 hours.

These tests cover materialization visibility, append-only guards, spec freezing,
operational pause, reapplication, missing/late anchors, irreversible censoring,
duplicate-anchor rejection in both insertion orders, idempotency, endpoint ordering, the 30-minute boundary, direction symmetry, and
application-role privileges. They do not establish production pg_cron behavior,
source-table uniqueness/immutability, multi-session concurrency, query performance,
or production PostgreSQL version/extension parity. Deployment remains subject to
the PR's active scientific review restriction.

## Review boundaries

The duplicate guard fails the collector transaction visibly before admission;
it does not select a replacement anchor, remove source rows, or invent an outcome.
The legacy `anchor_admitted` field is retained for compatibility. New consumers
should use `anchor_available`, `candidate_admitted`,
`candidate_pending_materialization`, and `anchor_ambiguous`.
The frozen specification permits status changes only. Evidence tables reject
ordinary UPDATE, DELETE, and TRUNCATE, including owner-issued DML, but PostgreSQL
superusers can still disable triggers or change DDL. This is not tamper-proof storage.
