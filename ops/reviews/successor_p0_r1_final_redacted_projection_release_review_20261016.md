# R1 exact redacted-reader security diff — review package handoff
**2026-10-16 | DRAFT PR #341 | NO production access authorization | USD $0**

## Review package status
Exact `R1_FORWARD_DO_NOT_EXECUTE.sql`, `R1_ROLLBACK_DO_NOT_EXECUTE.sql`,
`R1_review_manifest.json`, `R1_REVIEW_NOTES.md`, and
`verify_r1_static.py` have been prepared as **offline conversation
attachments** for owner/DBA review. **Neither SQL file is applied or added
to the production migration directory.** The executable-style SQL was not
published to this GitHub branch; its publication was blocked, and the
owner-facing offline attachments are the canonical SQL proposal for this
review. Do not infer a SQL hash or exact statement from this Markdown
summary alone.

Local static symmetry review found 12 source-table role-specific SELECT
policies, **two additional projection-owner RLS policies** (14 total),
12 restricted reader column grants, two projection-owner grants, two
read-only redacted views and an inverse rollback. Static verification is
not a PostgreSQL server integration rehearsal, a security signoff or
permission for the SQL editor to run migrations.

## Finalized logical redaction
- **Separate no-password scoped LOGIN reader**
  `alpha_hunter_p2_readonly`, `NOINHERIT/NOBYPASSRLS`, default
  `statement_timeout=12s`, read-only default transaction and no source
  DML, DDL, role creation or direct raw JSON privileges. It must receive a
  secret only in a future **separately authorized** secure provisioning step.
- **Separate NOLOGIN projection-definer role**
  `alpha_hunter_p2_projection_owner`: cannot bypass source RLS, owns
  no legacy source table, and may SELECT only the listed snapshot columns
  plus raw `payload` on two legacy snapshot relations. It has two
  exact role-specific SELECT RLS policies in addition to the reader's
  policies. The reader is **not a member** of this role.
- **Dedicated new schema `ah_p2_ro`** with security-barrier,
  **definer-rights** views `parent_snapshot_v01` and
  `symbol_quote_v01`, each owned by the NOLOGIN projection owner.
  Explicit `security_invoker=false` is intentional: a security-invoker
  view would require granting the reader base `payload` access,
  defeating the field-level redaction. Definer role remains bound by
  source RLS, and the views grant the reader SELECT only on projected
  fields, not raw JSON or full strategy payload. Reviewers must verify
  effective RLS and role privileges on actual selected PG version.
- Parent view exposes source run identity `run_source`, `git_commit`,
  `config_sha256`, scientific fingerprint fields and declared symbol
  count/error count. Child view exposes run/symbol, visible source
  state/flags, *text* best bid/ask, quote source/status, exchange/ticker
  and latest-trade timestamp, and source clock skew. It exposes **no
  full order-book depth arrays, private Bitget trade identifiers,
  mailbox recipient, secret or raw JSON**.
- No `paper_only=true` RLS row filter: unexpected non-paper flags
  must remain visible as errors. Missing RLS policy, zero restricted
  reader rows due to policy denial, missing parent validation identity,
  malformed timestamp/price or unsupported source cause
  `SOURCE_UNKNOWN/INCOMPLETE`, **never** monitoring PASS. Five parent
  snapshots in the then-recent read-only audit lacked validation identity;
  this is a real fail-closed coverage concern.
- The proposed views are **source projections only**, not independent
  signed capture of real venue quote bytes. They do not establish
  per-position 35-minute continuity or deliver alerts.

## Security/DBA blockers before an approval request
1. Exact SQL scripts must undergo **full offline PG16+/PG17 DDL/RLS tests**
   as submitted, with restricted-role SELECT access, denial of raw JSON
   and all other nonapproved columns, zero source DML/DDL/role escalation,
   missing-policy fail closed, anomalous source rows and the 1.5-unit
   NMR-style partial visible. Verify migration executor may CREATE ROLE,
   CREATE SCHEMA AUTHORIZATION and ALTER VIEW OWNER; a generic Supabase
   SQL editor's capability **must not be assumed**.
2. Confirm the live schema has unchanged 12 physical sources, their
   columns, RLS enabled and original policy baseline; a preflight
   mismatch must abort in its own transaction. Confirm rollback drops
   only new role-specific policies, grants, views, schema and roles,
   all with dependency-safe RESTRICT behavior and without deleting
   source rows or evidence. Validate rollback via repeated row/catalog
   snapshots, without touching scientific R10 source state.
3. Signed-off privacy assessment for each exposed output field and for
   the projection-definer raw JSON grant; strictly scoped, separate
   password/secret rotation later. Independently validate TLS,
   same-database repeatable-read snapshot consistency and bounded load
   against Primary Hourly before any real reader session.
4. Effective writer root cause for `57014` is **not proven**.
   The trigger cascade/large strategy observation table is a
   supported performance *hypothesis*. Frozen time budgets remain
   SQL 12s, HTTP 15s, max position monitoring gap **2100s**.
5. Independently persistent journal, external sentinel, verified email
   delivery and 72 real forward hours belong to **separate R3 and R4
   approvals**. P3 attributable cost/scientific order promotion remains
   blocked. Production R10 retains four original integrity failures,
   halted admissions and the unprotected partial NMRUSDT residual.

**R1 release verdict: design/field mapping READY FOR HUMAN REVIEW; exact DDL
PG integration/DBA signoff OUTSTANDING. NO execution authority granted.**
**R2–R4 remain unapproved. Primary Hourly unchanged. No spending.**
