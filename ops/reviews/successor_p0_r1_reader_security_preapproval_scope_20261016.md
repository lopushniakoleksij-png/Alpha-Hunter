# R1 proposed production reader scope — PRE-APPROVAL ONLY
**2026-10-16 | PR #341 DRAFT | not an executable migration | zero spend**

Owner permission to review a change request is not permission to run the
role/grant/policy migration. No credentials/passwords, keys, recipient address,
full JSON payload, source row IDs or executable SQL CREATE statements are
provided in this document.

## Required security approach
A new dedicated PostgreSQL **LOGIN** `alpha_hunter_p2_readonly` (placeholder,
NOT present/created) must be `NOINHERIT`, `NOBYPASSRLS`,
`NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, `NOREPLICATION`,
no privileged memberships, direct/session TLS endpoint and one
`REPEATABLE READ READ ONLY` snapshot transaction. GRANT only `CONNECT`
and schema `USAGE`; all source SELECT grants must be explicit **column
scoped**. No table-wide `SELECT *`, INSERT, UPDATE, DELETE, DDL, sequence,
function writer EXECUTE, role escalation, unauthorised default privileges,
bypass service-role JWT, or app-wide shared secrets.

For **each of all 12** base-source tables, reviewers must confirm:
1. Column allowlist below is sufficient and contains no unnecessary financial
   account/PII fields.
2. A **role-specific `FOR SELECT TO alpha_hunter_p2_readonly USING (true)`**
   RLS policy allows all source rows (including flagged anomalous rows) but
   only to this exact role; do NOT rely on broad PUBLIC grants or a
   `paper_only=true` filter. No policy / empty unexpectedly =
   `ACCESS_UNKNOWN`, never no residuals.
3. Row-level source order, entry/exit fills, 3 quarantines, protections,
   events and exit attempts are read as of the **same verified DB snapshot**.
   Source table count, role identity, DB clock, schema version, and
   manifest digest are recorded. Server-side read cannot invent producer
   authority or independently durable observation receipts.

## Proposed minimal per-table SELECT COLUMN ALLOWLIST
These are *review candidates*, not grants. Names come from actual
`information_schema.columns` at 2026-10-16 UTC.

| Physical table (`public.` prefix) | Proposed SELECT columns | Sensitive JSON status |
| --- | --- | --- |
| `alpha_hunter_paper_orders_v02` | `order_id,decision_id,submitted_at_utc,symbol,direction,order_type,quantity,paper_only,exchange_authority,trade_permission,order_path,successor_activation_id,successor_spec_id,successor_scientific_fingerprint_sha256,successor_source_run_id` | Exclude `evidence` until separately reviewed |
| `alpha_hunter_paper_fills_v02` | `fill_id,order_id,decision_id,fill_sequence,filled_at_utc,quantity,source_run_id,paper_only,exchange_authority,trade_permission,order_path` | No JSON required for residual census |
| `alpha_hunter_paper_exit_fills_v04` | `exit_fill_id,entry_order_id,decision_id,source_run_id,triggered_protective_order_id,protection_type,filled_at_utc,quantity,paper_only,exchange_authority,trade_permission,order_path` | No financial/PnL metrics required |
| `alpha_hunter_paper_exit_attempts_v04` | `attempt_id,entry_order_id,decision_id,source_run_id,observed_at_utc,symbol,direction,outcome,triggered_protection_type,best_bid,best_ask,best_bid_size,best_ask_size,paper_only,exchange_authority,trade_permission,order_path` | Exclude `evidence` and `blockers` pending independent quote/incident provenance review |
| `alpha_hunter_paper_protective_orders_v03` | `protective_order_id,entry_order_id,decision_id,activated_by_fill_id,created_at_utc,symbol,direction,protection_type,side,trigger_price,quantity,reduce_only,status,paper_only,exchange_authority,trade_permission,order_path` | Exclude `evidence` by default |
| `alpha_hunter_paper_events_v01` | `event_id,decision_id,sequence,occurred_at_utc,event_type,state,paper_only,exchange_authority,trade_permission,order_path` | Exclude `payload` by default |
| `alpha_hunter_paper_exit_activation_v04` | `activation_id,activated_at_utc,release_git_commit,paper_only,exchange_authority,trade_permission,order_path` | Exclude `evidence` by default |
| `alpha_hunter_paper_entry_quarantine_v06` | `order_id,decision_id,symbol,quarantined_at_utc,reason,paper_only,exchange_authority,trade_permission,order_path` | Exclude `evidence` pending reason-policy review |
| `alpha_hunter_paper_exit_quarantine_v04` | `entry_order_id,decision_id,symbol,protection_created_at_utc,quarantined_at_utc,reason,paper_only,exchange_authority,trade_permission,order_path` | Exclude `evidence` pending reason-policy review |
| `alpha_hunter_paper_reconciliation_quarantine_v04` | `order_id,decision_id,symbol,submitted_at_utc,quarantined_at_utc,reason,paper_only,exchange_authority,trade_permission,order_path` | Exclude `evidence` pending reason-policy review |
| `alpha_hunter_snapshots` | `run_id,collected_at_utc,version,product_type,symbol_count,error_count,created_at` | **Blocking gap:** `validation_identity` lives inside `payload`; must review redacted projection before source-run proof |
| `alpha_hunter_symbol_snapshots` | `run_id,symbol,collected_at_utc,state,previous_state,trade_permission,direction,last_price,open_interest,funding_rate,data_integrity_score,error,created_at` | **Blocking gap:** raw public-venue quote/strategy source bytes live in `payload`; need audited redacted projection or separately signed source receipt |

**Important gap to resolve BEFORE ANY R1 GRANT:** A source-manifest reader
without redacted `snapshots.payload.validation_identity` and vetted quote
provenance is insufficient to independently qualify the scanner or the
prospective 72-hour observer. Do not grant entire unrestricted JSON payload
just to eliminate the gap. Design a reviewed security-invoker, **read-only
projection** that exposes the minimum allowlisted keys, or have the security
reviewer explicitly approve necessary JSON columns after privacy audit.
Every projection/view depends on underlying RLS and effective role grants;
zero rows can mean policy denial. This R1 proposal intentionally remains
incomplete until that review.

## Negative preflight and rollback
**Preflight, only after a later explicit R1 approval:** security reviewer
pins exact SQL role/grants/policies + projection definition, no undefined
wildcards; inspect source policies and privileges before/after; test role
identity and session/transaction read-only, TLS certificate verification,
row count/manifest equality against privileged independent reference under
a bounded DB snapshot. Check an old positive **NMR-like partial** survives
with 1.5 entry minus 0 exit and remains classified as UNPROTECTED. Deliberate
missing one-table RLS policy must return SOURCE_ACCESS_UNKNOWN (never 0).
Deny writes/DDL/GRANT/SET ROLE/other-project columns. No unreviewed
read/quote/ticker/raw private data may be exported.

**Rollback, not executed:** disable the *separate* successor observer first,
invalidate and rotate the reader credential, revoke narrowly scoped policies,
column SELECT permissions and DB/schema usage, then remove the new dedicated
role only after verifying no dependency; remove/revoke redacted projection
as appropriate. Re-read physical sources with separately approved
privileged verifier to confirm ledger/R10 counts and scientific fingerprints
untouched; preserve immutable incident receipts and source historical
records. No `DROP` of legacy R10 tables, no deletes, no backfill.

**Cost:** No new hardware, connection, endpoint, provider, trial or
subscription may be created without separately approved pricing and
billing. USD0 currently authorized; USD25/mo planning ceiling only.

**Formal R1 approval status: NOT REQUESTED/NOT GRANTED.**
**R2 writer, R3 custody/real email, R4 72h pilot: BLOCKED.**
**NMR/unprotected residual, 57014 child timeouts: unresolved.**
