# R1 V3 least-privilege ownership correction — review checkpoint
**2026-10-16. NO production approval; DRAFT PR #341 only. USD $0 new spend.**

## Exact versioned artifacts and protection of original V2
The exact owner-requested R1 V2 SQL **remains unchanged and archived** in
ChatGPT Library `/Trading/Alpha-Hunter/R1-Security-Review` as V2, V2.1 and
V2.2. A new, **separate, offline** V3 review package is saved at the same
location: `Alpha_Hunter_R1_V3_Ownership_Correction_Review_20261016.zip`.
The production-like V3 DDL is **not published to GitHub**, installed as a
migration, or executed against production. Do not infer execution authority
from this markdown design note.

| SQL proposal, exact frozen bytes | SHA256 |
|---|---|
| V2 forward, **unchanged** | `b6e33d3cd8ae2b8fabf48891f7c4c42c7c455b6395474dc956feb3cfdf613594` |
| V2 rollback, **unchanged** | `eae646a519f06eff615d66a3ed093f79d414b12ddcb86eabd773617425ce0d1a` |
| V3 NEW forward, **not executed** | `c6d29daf35ab51283182312117ac367a4ad04ce950bd9950a448ceb5e64ccae7` |
| V3 NEW rollback, **not executed** | `3e289764bae0fe3ff790485a5fe2b88839a1da54ef85ce02468b13dd28b98fa9` |

Archive SHA256: `b34f517b9dcdab4acebecb77dadc4c856b17d4d7fa2e281131fa350600c19a4a`.
**V3 offline structural guards: 32/32 PASS**, not executable SQL integration.

## Smallest corrected ownership model (tested synthetically)
**Previous verified blocker:** the actual production `postgres` inspection
principal is NOT SUPERUSER but has CREATEROLE. PG16 grants a newly created
NOLOGIN role's creator ADMIN membership by default, **SET FALSE** and
**INHERIT FALSE**; thus the V2 `CREATE SCHEMA ... AUTHORIZATION owner`
and `ALTER VIEW OWNER TO owner` assumptions fail under a non-superuser
migrator without explicit membership rights.

**V3 proposed change:**
1. Create dedicated `alpha_hunter_p2_readonly` **NOLOGIN** and
   `alpha_hunter_p2_projection_owner` **NOLOGIN, NOBYPASSRLS** exactly
   as in V2, with the same 12 named source tables and source role RLS.
2. Non-superuser CREATEROLE migration principal temporarily obtains
   `SET TRUE, INHERIT FALSE` permission for projection owner. The
   migrator, which has an approved database CREATE privilege, creates
   `ah_p2_ro` **AUTHORIZATION owner**. Owner does NOT get
   database-wide CREATE.
3. With `SET ROLE owner`, create the two security-barrier
   `security_invoker=false` redacted views **as owner** and grant only
   their SELECT and the schema's USAGE to the NOLOGIN reader. This
   eliminates `ALTER VIEW OWNER`. `RESET ROLE`, then remove the
   **temporary SET membership**; verify that NO SET or INHERIT ability
   remains. Preserve NOLOGIN, source RLS, explicit column SELECT grants
   and all existing monitoring/timeout caps.
4. **Important residual privilege:** PG16 retains the creator's
   automatic **ADMIN TRUE / SET FALSE / INHERIT FALSE** membership.
   It permits the CREATEROLE actor to *re-grant* SET privilege later.
   This remaining administrative capability is **not** zero membership
   and requires independent DBA/security approval and audit.
5. In V3 rollback, the migrator temporarily uses automatic ADMIN
   membership to regain SET, uses `SET ROLE owner` to revoke the two
   view grants and schema grant and DROP the two views/schema with
   **RESTRICT**, restores migration role, removes all source policies
   and grants, then drops owner last. An *early* REVOKE during rollback
   caused `dependent privileges exist` PG16 failure and is specifically
   avoided. Never substitute CASCADE.

## Evidence — isolated GitHub PostgreSQL16 CI, not exact V3 execution
Existing zero-spend
`.github/workflows/successor-pg16-isolated-review-v01.yml`
runs `ops/reviews/successor_pg16_r1_temporary_setrole_lifecycle_v01.py`
in a fresh localhost-only PG16 database with synthetic roles/data,
without exchange or Supabase credentials.

**Confirmed dedicated result:**
[PG16 run 38891725355](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/38891725355)
has `R1_ISOLATED_PG16_TEMPORARY_SETROLE_FORWARD_ROLLBACK_PASS`.
Verifies NOLOGIN/nonbypass owner, non-superuser migrator, temporary
role SET permission then removal, automatic ADMIN-only grant precisely
classified, dedicated owner-owned redacted view, denied reader raw JSON
and source UPDATE, missing source identity preserved as NULL, 2/2
synthetic source rows unchanged, and owner-role deletion by a non-superuser
CREATEROLE migrator after views/schema are dropped.

**All 5/5 exact-head CI workflows passed**, including full Python suite
**1,402 tests and six subtests** on
[run 38891725442](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/38891725442);
R8 reconciliation, P02 and P03 isolated custody passed as separate
research checks.

**NOT PROVEN:** Exact V3 DDL forward and rollback executed in PostgreSQL16/17
on a fixture mirroring all 12 relations; effective Supabase non-superuser
ability to create source-table policies; stored ownership/GRANT chains for
every table; safe real reader activation; proof of a production observer,
independent source/venue quotes, delivered email or 35-minute continuity.
No human independent DBA/security reviewer has signed off. The synthetic
CI has `exact_V2_or_V3_production_SQL_executed:false` and
`external_DBA_signoff:false`.

## Immutable release and next gate
Owner must authorize **nothing** until the *exact unchanged V3 file hashes*
are rehearsed under production-equivalent non-superuser principals in
disposable PG16 AND PG17, with source-grant/RLS negative tests and
rollback drift/row preservation, then a separate identified human
DBA/security signature. Only after these can the owner be asked for a
separate, narrow R1 production access decision. R2/R3 observer/custody,
R4 72h pilot, P3 profitability, trading, credentials and new spending
remain **NO-GO**.

Primary Hourly cron is never stopped or changed. R10 admission halt,
four original integrity failures, historic unprotected 1.5-unit NMRUSDT
**paper** residual, child write SQLSTATE 57014 failures, and frozen
12s SQL / 15s HTTP / 2,100s monitoring limits remain in force.
