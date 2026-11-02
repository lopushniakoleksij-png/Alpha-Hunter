# Alpha Hunter R1 — original V3 archive preflight and safe source-reader gate

**23 October 2026, 13:37 UTC | Draft PR #341 | NO deployment | NO new infrastructure | $0**

## What was independently checked without exposing SQL or editing Supabase

The *original, exact-byte* user Library archive was recovered for review;
the archived V3 scripts have **not** been copied to this GitHub repository
or the auto-deploy production branch. Exact bytes (including final newline)
were hashed locally against the pre-registered review hashes:

| Sealed offline file | Size | Verified SHA-256 |
| --- | ---: | --- |
| R1_FORWARD_V3_DO_NOT_APPLY.sql | 14,061 | `c6d29daf35ab51283182312117ac367a4ad04ce950bd9950a448ceb5e64ccae7` |
| R1_ROLLBACK_V3_DO_NOT_APPLY.sql | 7,640 | `3e289764bae0fe3ff790485a5fe2b88839a1da54ef85ce02468b13dd28b98fa9` |

The exact forward and rollback **remain private Library review files**; a
separate GitHub rollback review copy has previously been shown to have a
different final-newline size and **must not be treated as the exact source**.

A new read-only `pg_catalog` / `pg_attribute` comparison at **2026-10-23
13:37:34 UTC** on the existing PostgreSQL 17.6 database confirmed:

- All 12 named base relations exist, each owned by `postgres`, with RLS
  enabled and **zero pre-existing SELECT policies**.
- No R1 dedicated source-reader/projection owner roles and no
  `ah_p2_ro` schema have been provisioned.
- All **14** column-level GRANT sets in the original V3 forward have
  matching **14** REVOKE sets in its original V3 rollback, preserving
  column order and intended role; **160/160** referenced column names
  still exist in the production table definitions.
- All **14** proposed named policy creations have matching **14**
  rollback drops. The designated reader in the ORIGINAL forward begins
  as `NOLOGIN`: no real credentials, no activated reader.
- This compares source *metadata only*: it does **not** execute DDL,
  inspect sensitive row values or demonstrate actual effective viewer RLS
  privileges.

**Narrow verdict: R1 ARCHIVE STATIC SOURCE PRE-FLIGHT = PASS.**
This is NOT PG16/PG17 byte-for-byte migration/rollback execution PASS,
human DBA/security signoff, or an R1 production authorization.

## Safe dual-engine synthetic role-test work

Existing isolated 12-source security/RLS negative regression was extended
to support both PostgreSQL 16 and PostgreSQL 17, using:
- a new draft-only `R1 Isolated PG16 PG17 Least-Privilege Source Review`
  GitHub Actions matrix; both environments are disposable local containers
  with all production Supabase/Bitget secrets empty;
- restricted reader column grants and all 12 modeled RLS relations;
  missing policy yields UNKNOWN, not zero positions;
- synthetic unprotected 1.5-unit NMR-style partial outside the managed
  security-invoker view, and a visible anomalous `paper_only=false` row;
- negative SELECT raw/excluded-column, DML/DDL, CREATE ROLE, SET ROLE,
  plus read-only repeatable-read snapshot.

**This is a synthetic model and does not execute the archived exact V3 files.**
Its results cannot release R1 regardless of CI success.

## Outstanding mandatory release gates

1. Execute **both exact original hash-verified V3 files** against a fully
   isolated, production-equivalent 12-table synthetic database under a
   **non-superuser CREATEROLE migration identity** on PostgreSQL 16
   and 17. This requires a transfer method that DOES NOT publish protected
   archived DDL to an unapproved public repo. Keep V3 immutable; a defect
   creates V4 rather than modifying the archived hash. Test rollback under
   the same effective privileges, writer denial, membership cleanup, view
   owner RLS and untouched source row hashes.
2. Separate real DBA and security officer signatures against exact V3
   hashes and test artifacts. Owner approval for an exact scoped R1
   production role change is **NOT** inferred from the permission to do
   research or a request to proceed to the next priority.
3. Only after explicit separate owner approval: provision credential and
   TLS-verified dedicated source reader; confirm real single-snapshot
   all-ledger visibility and load against unchanged Primary Hourly, with
   no production writer changes or bypass-RLS access.
4. Separately approve distinct long-lived custody, real recipient/channel
   validation, external dead-man and spending. **None are present here**.
   Synthetic alert simulations and expiring GitHub artifacts are not
   durable operational delivery or source authenticity.
5. An approved successor-only 72-hour *forward* safety window still must
   be demonstrated without backfill; original R10 35-minute maximum,
   30-day scientific clock, four integrity failures and admissions halt
   must remain unchanged. No trading/performance promotion.

**R1 operational verdict: NO-GO / REQUIRES INDEPENDENT SECURITY RELEASE.**
No test reset, cron pause/restart, main merge, production migration, reader
login, new resource, alert sent, real trade, history changes or money spent.
